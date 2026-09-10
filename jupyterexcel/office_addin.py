"""Generate and serve an Office.js add-in from decorated Jupyter notebooks."""

import ast
import json
import logging
import os
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import quote
from .metadata import validate_metadata


CUSTOM_FUNCTION_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/office-js/"
    "custom-functions.schema.json"
)


@dataclass
class Parameter:
    name: str
    type: str = "any"
    optional: bool = False
    description: str = ""
    dimensionality: str = "scalar"
    repeating: bool = False


@dataclass
class NotebookFunction:
    notebook: str
    python_name: str
    excel_name: str
    description: str
    result_type: str = "any"
    parameters: list = field(default_factory=list)
    kind: str = "jupyter"
    result_dimensionality: str = "scalar"

    @property
    def function_id(self):
        # Office IDs allow only letters, numbers, and periods.
        value = "".join(c if (c.isascii() and c.isalnum()) or c == "." else "." for c in self.excel_name)
        return value.upper().strip(".")


def _literal(node, default=None):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return default


def _decorator_name(node):
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _function_from_ast(node, decorator, notebook):
    kind = _decorator_name(decorator)
    if kind not in {"jupyter_function", "ribbon_function"}:
        return None
    call = decorator if isinstance(decorator, ast.Call) else None
    keywords = {item.arg: _literal(item.value) for item in (call.keywords if call else [])}
    positional = [_literal(item) for item in (call.args if call else [])]
    if kind == "ribbon_function":
        excel_name = positional[0] if positional else keywords.get("name", node.name)
        description = "Ribbon command: " + str(excel_name)
    else:
        excel_name = keywords.get("name") or (positional[0] if positional else node.name)
        description = keywords.get("description") or ast.get_docstring(node) or node.name
    arguments = node.args.posonlyargs + node.args.args
    if kind == 'jupyter_function' and call:
        for keyword in call.keywords:
            if keyword.arg in {'parameter_types', 'parameter_dimensionality', 'result_type', 'result_dimensionality'}:
                try:
                    ast.literal_eval(keyword.value)
                except (ValueError, TypeError):
                    raise ValueError(f'{notebook}: {node.name}: {keyword.arg} must be a literal for static discovery.') from None
    parameter_types = keywords.get('parameter_types')
    parameter_dimensionality = keywords.get('parameter_dimensionality')
    result_type = keywords.get('result_type', 'any')
    result_dimensionality = keywords.get('result_dimensionality', 'scalar')
    if kind == 'jupyter_function':
        validate_metadata([arg.arg for arg in arguments + node.args.kwonlyargs + ([node.args.vararg] if node.args.vararg else [])],
                          parameter_types, parameter_dimensionality, result_type, result_dimensionality)
    parameter_types = parameter_types or {}
    parameter_dimensionality = parameter_dimensionality or {}
    if kind == 'jupyter_function' and node.args.vararg and (node.args.kwonlyargs or node.args.kwarg):
        raise ValueError('Repeating worksheet parameters must be last; keyword parameters are unsupported.')
    defaults_start = len(arguments) - len(node.args.defaults)
    parameters = []
    for index, argument in enumerate(arguments):
        parameters.append(Parameter(
            name=argument.arg,
            type=parameter_types.get(argument.arg, "any"),
            dimensionality=parameter_dimensionality.get(argument.arg, "scalar"),
            optional=index >= defaults_start,
            description=argument.arg,
        ))
    if node.args.vararg:
        arg = node.args.vararg.arg
        parameters.append(Parameter(name=arg, type=parameter_types.get(arg, 'any'),
                                    dimensionality=parameter_dimensionality.get(arg, 'scalar'),
                                    description=arg, repeating=True))
    return NotebookFunction(
        notebook=notebook,
        python_name=node.name,
        excel_name=str(excel_name),
        description=str(description),
        result_type=result_type,
        result_dimensionality=result_dimensionality,
        parameters=parameters,
        kind="ribbon" if kind == "ribbon_function" else "jupyter",
    )


def scan_notebook(notebook, path):
    found = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                item = _function_from_ast(node, decorator, path)
                if item:
                    found.append(item)
                    break
    return found


def discover_notebooks(contents_manager):
    """Find decorated functions in all notebooks visible to this server user."""
    functions = []

    def visit(path=""):
        model = contents_manager.get(path, content=True)
        if model.get("type") == "notebook":
            functions.extend(scan_notebook(model["content"], model["path"]))
            return
        if model.get("type") == "directory":
            for child in model.get("content") or []:
                if child.get("type") in {"directory", "notebook"}:
                    visit(child["path"])

    visit("")
    seen = set()
    unique = []
    for item in functions:
        key = item.function_id
        if item.kind == "jupyter" and key in seen:
            raise ValueError("Duplicate @jupyter_function Excel name: %s" % key)
        if item.kind == "jupyter":
            seen.add(key)
        unique.append(item)
    return unique


def functions_metadata(functions):
    entries = []
    for item in functions:
        if item.kind != "jupyter":
            continue
        entries.append({
            "id": item.function_id,
            "name": item.function_id,
            "description": item.description,
            "parameters": [
                {
                    "name": parameter.name,
                    "description": parameter.description,
                    "type": parameter.type,
                    "dimensionality": parameter.dimensionality,
                    **({"repeating": True} if parameter.repeating else {}),
                    **({"optional": True} if parameter.optional else {}),
                }
                for parameter in item.parameters
            ],
            "result": {"type": item.result_type, "dimensionality": item.result_dimensionality},
        })
    return {"$schema": CUSTOM_FUNCTION_SCHEMA, "functions": entries}


def client_configuration(base_url, hub_user=None):
    """Public API connection information only; credentials are supplied at runtime."""
    base = base_url.rstrip('/')
    hub_base = base.split('/user/', 1)[0]
    return {'apiBase': base, 'hubUser': hub_user, 'hubApiUrl': hub_base + '/hub/api/user'}


def functions_javascript(functions, base_url, template_dir=None, hub_user=None):
    """Bundle reusable runtime code and notebook-specific registrations."""
    templates = Path(template_dir) if template_dir else Path(__file__).parent / 'addin_template'
    runtime = (templates / 'jupyter-runtime.js').read_text(encoding='utf-8').rstrip()
    template = (templates / 'functions.js').read_text(encoding='utf-8')
    registrations = []
 
 
    for item in (f for f in functions if f.kind == 'jupyter'):
        endpoint = base_url.rstrip('/')  + '/Excel/' + quote(item.function_id, safe='')
        # Office may append an invocation object after the worksheet parameters.
        arguments = f'args.slice(0, {len(item.parameters)})'
        if item.parameters and item.parameters[-1].repeating:
            index = len(item.parameters) - 1
            arguments = f'args.slice(0, {index}).concat(args[{index}] || [])'
        registrations.append('CustomFunctions.associate(%s, (...args) => jupyterExcelCall(%s, %s));' % (json.dumps(item.function_id), json.dumps(endpoint), arguments))
    for marker in ('{{FUNCTIONS_RUNTIME}}', '{{FUNCTION_REGISTRATIONS}}'):
        if template.count(marker) != 1:
            raise ValueError('functions.js template must contain exactly one ' + marker)
    config = client_configuration(base_url, hub_user)
    prefix = 'globalThis.JupyterExcelConfig = ' + json.dumps(config) + ';\n'
    return prefix + template.replace('{{FUNCTIONS_RUNTIME}}', runtime).replace('{{FUNCTION_REGISTRATIONS}}', '\n'.join(registrations))


def public_url(server_app):
    configured = os.environ.get("JUPYTEREXCEL_PUBLIC_URL")
    if configured:
        return configured.rstrip("/")
    logger = getattr(server_app, "log", None) or logging.getLogger(__name__)
    logger.error(
        "JUPYTEREXCEL_PUBLIC_URL is not set or is empty; "
        "continuing with a URL derived from the Jupyter server settings."
    )
    scheme = "https" if getattr(server_app, "certfile", "") else "http"
    host = getattr(server_app, "ip", "") or "localhost"
    if host in {"0.0.0.0", "::", "*"}:
        host = "localhost"
    port = getattr(server_app, "port", 8888)
    base_path = server_app.web_app.settings.get("base_url", "/").strip("/")
    return "%s://%s:%s%s" % (scheme, host, port, ("/" + base_path) if base_path else "")
