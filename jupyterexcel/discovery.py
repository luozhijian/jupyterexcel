"""Select notebooks through ContentsManager using root-level project settings."""
import inspect
import json

CONFIG_NAME = 'jupyterexcel-config.json'


async def _resolved(value):
    return await value if inspect.isawaitable(value) else value


def _includes(config):
    def invalid(message):
        raise ValueError(CONFIG_NAME + ': ' + message)

    if not isinstance(config, dict):
        invalid('expected a JSON object.')
    discovery = config.get('discovery', {})
    if not isinstance(discovery, dict):
        invalid('discovery must be an object.')
    if set(discovery) - {'include'}:
        invalid('unknown discovery setting; use discovery.include.')
    if 'include' not in discovery:
        return [('', True)]
    entries = discovery['include']
    if not isinstance(entries, list):
        invalid('discovery.include must be a list.')
    result = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {'folder', 'recursive'}:
            invalid('each include entry must contain folder and optional recursive.')
        folder = entry.get('folder')
        recursive = entry.get('recursive', False)
        if not isinstance(folder, str) or not folder.strip():
            invalid('folder must be a nonempty relative path; use . for the root.')
        if not isinstance(recursive, bool):
            invalid('recursive must be true or false.')
        if folder.startswith('/') or '\\' in folder or ':' in folder or any(p in {'', '..'} for p in folder.split('/')) or any(c in folder for c in '*?[]'):
            invalid('folder must be a relative folder path using /, without .. or wildcards: ' + folder)
        path = '/'.join(p for p in folder.split('/') if p != '.')
        result.append((path, recursive))
    return result


async def read_project_config(contents):
    root = await _resolved(contents.get('', content=True))
    snapshot = getattr(contents, '_jupyterexcel_config', None)
    if snapshot is not None:
        import copy
        return copy.deepcopy(snapshot['config']), root
    # Standalone discovery tools can also select the central file.
    import os
    from .config import CONFIG_ENV, load_config
    if CONFIG_ENV in os.environ:
        return load_config()['config'], root
    config = {}
    if any(child.get('path') == CONFIG_NAME for child in root.get('content') or []):
        model = await _resolved(contents.get(CONFIG_NAME, content=True))
        if model.get('type') != 'file' or model.get('format', 'text') != 'text':
            raise ValueError(CONFIG_NAME + ': expected a UTF-8 JSON text file.')
        try:
            config = json.loads(model['content'])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(CONFIG_NAME + ': invalid JSON: ' + str(exc)) from exc


    if not isinstance(config, dict):
        raise ValueError(CONFIG_NAME + ': expected a JSON object.')
    return config, root


async def selected_notebooks(contents):
    """Return (complete relative path, model), deduplicated and sorted.

    Read the root listing first so absent config needs no failing get() and both
    synchronous and asynchronous ContentsManagers work. Unselected directories
    are never traversed. Unknown top-level sections are reserved for future use.
    """
    config, root = await read_project_config(contents)
    entries = _includes(config)

    models = {'': root}
    visited = set()
    notebooks = {}

    async def visit(path, recursive):
        if (path, recursive) in visited:
            return
        visited.add((path, recursive))
        if path not in models:
            models[path] = await _resolved(contents.get(path, content=True))
        model = models[path]
        if model['type'] != 'directory':
            raise ValueError(CONFIG_NAME + ': included folder is not a directory: ' + path)
        for child in sorted(model.get('content') or [], key=lambda item: item['path']):
            child_path = child['path']
            if child['type'] == 'notebook' and child_path not in notebooks:
                notebooks[child_path] = await _resolved(contents.get(child_path, content=True))
            elif child['type'] == 'directory' and recursive:
                await visit(child_path, True)

    for path, recursive in entries:
        await visit(path, recursive)
    return sorted(notebooks.items())
