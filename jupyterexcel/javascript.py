"""Static JavaScript notebook exports; no notebook code runs during discovery."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from functools import lru_cache


def is_javascript(notebook):
    from .profiles import notebook_language
    return notebook_language(notebook) == 'javascript'


@lru_cache(maxsize=64)
def _parse(cells):
    node = shutil.which('node')
    if not node:
        raise ValueError('JavaScript export discovery requires Node.js on the Jupyter server PATH.')
    result = subprocess.run([node, str(Path(__file__).with_name('jsdoc_parser.bundle.cjs'))],
                            input=json.dumps(cells), text=True, encoding='utf-8',
                            capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError(result.stderr.strip())
    return json.loads(result.stdout)


def scan_javascript(notebook, path):
    from .office_addin import NotebookFunction, Parameter
    from .metadata import validate_function_name
    sources = tuple(''.join(c.get('source', '')) if c.get('cell_type') == 'code' else ''
                    for c in notebook.get('cells', []))
    if not any('@excelFunction' in s or '@ribbonFunction' in s or '@jupyter_function' in s or '@ribbon_function' in s for s in sources):
        return []
    metadata = notebook.get('metadata', {})
    version = hashlib.sha256(json.dumps([sources, metadata.get('kernelspec', {}), metadata.get('jupyterexcel', {})], sort_keys=True).encode()).hexdigest()
    try:
        parsed = _parse(sources)
    except (ValueError, subprocess.TimeoutExpired) as error:
        raise ValueError(f'{path}: {error}') from error
    found = []
    for cell, items in enumerate(parsed, 1):
        for raw in items:
            from .profiles import profile_name, notebook_profile
            profile = profile_name(raw['execution_profile']) if 'execution_profile' in raw else (notebook_profile(notebook) if raw['execution'] == 'server' else None)
            if 'execution_profile' in raw and raw['execution'] == 'local':
                raise ValueError(f'{path}: local exports cannot specify a server execution profile.')
            def dimensions(kind):
                if kind in ('number', 'string', 'boolean'):
                    return kind, 'scalar'
                if kind in ('number[][]', 'string[][]', 'boolean[][]'):
                    return kind[:-4], 'matrix'
                raise ValueError(f'{path}, cell {cell}: Use scalar types or rectangular 2D arrays.')
            parameters, inputs = [], []
            for p in raw['inputs']:
                kind, dimension = dimensions(p['type'])
                if 'default' in p:
                    from .actions import validate_value
                    validate_value(p['default'], 'matrix' if dimension == 'matrix' else kind)
                parameters.append(Parameter(p['name'], kind, p['optional'], p['description'], dimension,
                                            default=json.dumps(p['default']) if 'default' in p else None))
                inputs.append(dict(name=p['name'], label=p['name'], description=p['description'],
                                   type='matrix' if dimension == 'matrix' else kind, source=p.get('selector', 'value'),
                                   **({'reference_only': True, 'max_cells': 1503 if p['selector'] == 'range' else 1} if p.get('selector') else {}),
                                   optional=p['optional'], javascript=True, **({'default': p['default']} if 'default' in p else {})))
            result_type, result_dimension = dimensions(raw['result'])
            status_only = raw.get('output') == 'status'
            if status_only and (result_type != 'string' or result_dimension != 'scalar'):
                raise ValueError('Status-only actions must return a string.')
            identifier = validate_function_name(raw['id'])
            form = dict(id=identifier, label=raw.get('label') or identifier,
                        button_text=raw.get('button_text') or ('Calculate' if raw['kind'] == 'jupyter' else 'Run'),
                        description=raw['description'], inputs=inputs,
                        output={'type': 'matrix' if result_dimension == 'matrix' else result_type,
                                'destinations': ['taskpane'] if status_only else ['taskpane', 'range'],
                                'default': 'taskpane', **({'status_only': True} if status_only else {})},
                        execution=raw['execution'], javascript=True, version=version,
                        help_url='help/generated/' + identifier + '.html')
            found.append(NotebookFunction(path, raw['name'], identifier, raw['description'], result_type,
                         parameters, raw['kind'], result_dimension, form if raw['kind'] == 'ribbon' else None,
                         language='javascript', execution=raw['execution'], source=raw['source'],
                         version=version, documentation=raw, form=form, execution_profile=profile))
    return found


def browser_exports(functions, base_url):
    lines = [Path(__file__).with_name('addin_template').joinpath('javascript-exports.js').read_text(encoding='utf-8')]
    if any(f.language == 'javascript' and 'JupyterExcelCharts' in f.source for f in functions):
        lines.insert(0, Path(__file__).with_name('addin_template').joinpath('sankey.bundle.js').read_text(encoding='utf-8'))
    for item in functions:
        if item.language != 'javascript':
            continue
        metadata = dict(item.form, parameters=[dict(name=p.name, type=p.type, optional=p.optional,
                        dimensionality=p.dimensionality) for p in item.parameters],
                        result_type=item.result_type,
                        endpoint=base_url.rstrip('/') + '/Excel/' + item.function_id)
        implementation = '(' + item.source + ')' if item.execution == 'local' else 'null'
        lines.append('globalThis.JupyterExcelJavaScript.register(' + json.dumps(metadata) + ', ' + implementation + ');')
    return '\n'.join(lines)
