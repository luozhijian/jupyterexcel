"""JSON-only deployment configuration and explicit configuration inspection."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import logging  

CONFIG_NAME = 'jupyterexcel-config.json'
CONFIG_ENV = 'JUPYTEREXCEL_CONFIG_FILE'
EXECUTION_DEFAULTS = dict(min_kernels=1, max_kernels=4, timeout_seconds=30,
    startup_timeout_seconds=60, queue_timeout_seconds=30, max_queue_size=1000,
    scale_up_utilization=0.8, utilization_window_seconds=5,
    queue_scale_up_after_seconds=1, scale_up_cooldown_seconds=1)
DEFAULTS = {
    'schema_version': 1,
    'server': {'public_url': None},
    'assets': {'directory': None, 'url': None},
    'addin': {'namespace': 'Jupyter'},
    'discovery': {'include': [{'folder': '.', 'recursive': False}]},
    'execution': EXECUTION_DEFAULTS,
    'hub': {'auto_start_users': []},
}
# Only set inside an initialized service kernel; the server keeps its snapshot
# on its own ContentsManager, so separate servers cannot share mutable settings.
_kernel_snapshot = None


def validate_execution(supplied):
    if not isinstance(supplied, dict) :
        raise ValueError('jupyterexcel-config.json: invalid execution settings.')

    diff_setting = set(supplied) - EXECUTION_DEFAULTS.keys()
    if diff_setting:
        raise ValueError('Unknown execution settings: ' + ', '.join(sorted(diff_setting)))
    settings = dict(EXECUTION_DEFAULTS, **supplied)
    for key, value in settings.items():
        if key == 'min_kernels' and type(value) is int and value == 0:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('execution.' + key + ' must be a positive finite number.')
    for key in ('min_kernels', 'max_kernels', 'max_queue_size'):
        if not isinstance(settings[key], int):
            raise ValueError('execution.' + key + ' must be an integer.')
    if settings['min_kernels'] > settings['max_kernels'] or settings['scale_up_utilization'] > 1:
        raise ValueError('Invalid kernel limits or utilization threshold.')
    return settings


def validate_users(value):
    if not isinstance(value, list) or any(not isinstance(u, str) or not u or
            any(c.isspace() or c in ':!/\\?#&=' for c in u) for u in value):
        raise ValueError('hub.auto_start_users must be an array of existing usernames.')
    return list(dict.fromkeys(value))


def validate(config, path):
    if not isinstance(config, dict) or set(config) - DEFAULTS.keys():
        raise ValueError('Expected a JSON object with known configuration sections.')
    version = config.get('schema_version', 1)
    if type(version) is not int or version != 1:
        raise ValueError('schema_version must be 1.')
    result = copy.deepcopy(DEFAULTS)
    for section, values in config.items():
        if section == 'schema_version':
            continue
        allowed = set(DEFAULTS[section])
        if section == 'execution':
            allowed |= {'profiles', 'defaults', 'default_profiles', 'total_max_kernels'}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError('Unknown or invalid settings in ' + section + '.')
        result[section].update(copy.deepcopy(values))
    for section, key in [('server', 'public_url'), ('assets', 'url')]:
        value = result[section][key]
        if not isinstance(value, str):
            raise ValueError(section + '.' + key + ' is required.')
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.netloc or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or any(c.isspace() for c in value)):
            raise ValueError(section + '.' + key + ' must be an absolute HTTPS URL without credentials, query or fragment.')
        result[section][key] = value.rstrip('/')
    directory = result['assets']['directory']
    if not isinstance(directory, str) or not directory.strip() or '://' in directory:
        raise ValueError('assets.directory must be a nonempty filesystem path.')
    destination = Path(directory)
    if not destination.is_absolute():
        destination = path.parent / destination
    result['assets']['directory'] = str(destination.resolve())
    namespace = result['addin']['namespace']
    if not isinstance(namespace, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9._]{0,31}', namespace.strip()):
        raise ValueError('addin.namespace must be 1-32 ASCII letters, digits, periods or underscores, starting with a letter.')
    result['addin']['namespace'] = namespace.strip()
    from .discovery import _includes
    _includes(result)
    for entry in result['discovery']['include']:
        entry.setdefault('recursive', False)
    execution = result['execution']
    result['execution'] = dict(validate_execution({key: execution[key] for key in EXECUTION_DEFAULTS}),
                               **{key: execution[key] for key in ('profiles', 'defaults', 'default_profiles', 'total_max_kernels') if key in execution})
    from .profiles import validate_profiles
    validate_profiles(result['execution'])
    result['hub']['auto_start_users'] = validate_users(result['hub']['auto_start_users'])
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate setting: ' + key)
        result[key] = value
    return result


def load_config(root=None, path=None):
    """Read exactly one file; explicit paths are for Hub setup and inspection."""
    selected = path if path is not None else os.environ.get(CONFIG_ENV)
    source = 'explicit path' if path is not None else CONFIG_ENV
    if selected is not None:
        if not str(selected).strip() or not Path(selected).is_absolute():
            raise ValueError(source + ' must be a nonempty absolute file path.')
        target = Path(selected).resolve()
    else:
        target = (Path(root) if root is not None else Path.cwd()).resolve() / CONFIG_NAME
        source = 'notebook root' if root is not None else 'current directory'
    try:
        logging.info('Loading JupyterExcel configuration from %s', target)
        raw = target.read_bytes()
        values = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_object,
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid number: ' + value)))
        effective = validate(values, target)
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(str(target) + ': ' + str(exc)) from exc
    return dict(path=str(target), source=source, sha256=hashlib.sha256(raw).hexdigest(), config=effective)


def config_report(snapshot):
    result = copy.deepcopy(snapshot)
    try:
        result['restart_required'] = hashlib.sha256(Path(snapshot['path']).read_bytes()).hexdigest() != snapshot['sha256']
    except OSError:
        result['restart_required'] = True
    return result


def show_config(path=None, *, root=None, server_app=None):
    """Print and return the selected path and full effective configuration.

    With server_app, or inside a managed service kernel, inspect the loaded
    server snapshot. Else inspect the file and explicitly label it as disk state.
    Pass root when an ordinary notebook's working directory differs from the
    server root, or path to inspect a particular central configuration.
    """
    snapshot = None
    if server_app is not None:
        snapshot = server_app.web_app.settings['jupyterexcel_config']
    elif path is None and root is None:
        snapshot = _kernel_snapshot
    loaded = snapshot is not None
    report = config_report(snapshot) if loaded else load_config(root=root, path=path)
    print('Configuration file: ' + report['path'])
    print('Selected by: ' + report['source'])
    print('State: ' + ('loaded server settings' if loaded else 'file on disk (running server settings not verified)'))
    if report.get('restart_required'):
        print('File changed or unavailable; restart Jupyter to apply changes.')
    print(json.dumps(report['config'], indent=2, ensure_ascii=False))
    return copy.deepcopy(report)
