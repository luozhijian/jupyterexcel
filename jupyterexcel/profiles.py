"""Execution environment metadata and deterministic kernelspec routing."""
import copy
import logging
import re


def profile_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9._-]*', value):
        raise ValueError('Execution profile must start with a letter and contain letters, digits, dots, underscores, or hyphens.')
    return value


def execution_profile(name):
    """Attach an environment requirement without wrapping the function."""
    name = profile_name(name)
    def decorate(function):
        existing = getattr(function, '__jupyterexcel_execution_profile__', name)
        if existing != name:
            raise ValueError('Conflicting execution profiles on ' + function.__name__)
        function.__jupyterexcel_execution_profile__ = name
        return function
    return decorate


def notebook_language(notebook):
    metadata = notebook.get('metadata', {})
    kernel = metadata.get('kernelspec', {})
    aliases = {'python': 'python', 'javascript': 'javascript', 'typescript': 'javascript', 'r': 'r'}
    languages = []
    for raw in (metadata.get('language_info', {}).get('name'), kernel.get('language')):
        if raw:
            language = aliases.get(raw.lower())
            if language is None:
                raise ValueError('Unsupported notebook language: ' + raw)
            languages.append(language)
    inferred = {'python3': 'python', 'deno': 'javascript', 'ir': 'r'}.get(kernel.get('name'))
    if inferred:
        languages.append(inferred)
    if len(set(languages)) > 1:
        raise ValueError('Conflicting notebook language and kernelspec metadata.')
    if languages:
        return languages[0]
    if kernel.get('name'):
        raise ValueError('Notebook with a custom kernelspec must declare its language.')
    # Preserve historical Python notebooks with no language metadata.
    return 'python'


def notebook_profile(notebook):
    settings = notebook.get('metadata', {}).get('jupyterexcel', {})
    if not isinstance(settings, dict):
        raise ValueError('metadata.jupyterexcel must be an object.')
    value = settings.get('execution_profile')
    return profile_name(value) if value is not None else None


def validate_profiles(execution):
    from .config import EXECUTION_DEFAULTS, validate_execution
    base = {key: execution[key] for key in EXECUTION_DEFAULTS if key in execution}
    defaults = execution.get('defaults', {})
    if not isinstance(defaults, dict) or set(defaults) - EXECUTION_DEFAULTS.keys():
        raise ValueError('execution.defaults contains unknown pool settings.')
    base = validate_execution(dict(base, **defaults))
    raw_profiles = execution.get('profiles', {})
    if not isinstance(raw_profiles, dict):
        raise ValueError('execution.profiles must be an object.')
    profiles = {
        'python-default': dict(base, language='python', kernel_name='python3', enabled=True, idle_shutdown_seconds=300),
        'javascript': dict(base, language='javascript', kernel_name='deno', enabled=True, min_kernels=0, max_kernels=2, idle_shutdown_seconds=300),
    }
    fields = set(EXECUTION_DEFAULTS) | {'language', 'kernel_name', 'enabled', 'idle_shutdown_seconds'}
    for name, settings in raw_profiles.items():
        profile_name(name)
        if not isinstance(settings, dict) or set(settings) - fields:
            raise ValueError('Unknown settings in execution profile ' + name)
        profile = dict(profiles.get(name, dict(base, min_kernels=0, enabled=True, idle_shutdown_seconds=300)), **copy.deepcopy(settings))
        if profile.get('language') not in {'python', 'javascript', 'r'}:
            raise ValueError(name + ': language must be python, javascript, or r.')
        if not isinstance(profile.get('kernel_name'), str) or not re.fullmatch(r'[A-Za-z0-9._-]+', profile['kernel_name']):
            raise ValueError(name + ': kernel_name must identify an installed Jupyter kernelspec.')
        if type(profile['enabled']) is not bool:
            raise ValueError(name + ': enabled must be boolean.')
        if profile['language'] == 'r' and profile['enabled']:
            raise ValueError(name + ': the R adapter is not implemented; keep this profile disabled.')
        if type(profile['idle_shutdown_seconds']) not in (int, float) or not 0 < profile['idle_shutdown_seconds'] < float('inf'):
            raise ValueError(name + ': idle_shutdown_seconds must be positive and finite.')
        profile.update(validate_execution({key: profile[key] for key in EXECUTION_DEFAULTS}))
        profiles[name] = profile
    total = execution.get('total_max_kernels', max(8, base['max_kernels'] + 2))
    if type(total) is not int or total < 1:
        raise ValueError('execution.total_max_kernels must be a positive integer.')
    if sum(p['min_kernels'] for p in profiles.values() if p['enabled']) > total:
        raise ValueError('Profile minimum kernel counts exceed total_max_kernels.')
    default_profiles = dict(python='python-default', javascript='javascript')
    overrides = execution.get('default_profiles', {})
    if not isinstance(overrides, dict) or set(overrides) - {'python', 'javascript', 'r'}:
        raise ValueError('execution.default_profiles maps languages to profile names.')
    default_profiles.update(overrides)
    for language, name in default_profiles.items():
        if name not in profiles or profiles[name]['language'] != language:
            raise ValueError('Default profile does not match language: ' + language)
    return profiles, default_profiles, total


class ProfileWarnings:
    """Server-scoped suppression shared by discovery and execution."""

    def __init__(self, logger=None):
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.seen = set()

    def resolve(self, function, notebook, profiles, defaults, legacy_python=False):
        name, fallback = resolve_profile(function, notebook, profiles, defaults,
                                         legacy_python, include_fallback=True)
        if fallback is not None and fallback not in self.seen:
            self.seen.add(fallback)
            path, kernel, language, profile, selected_kernel = fallback
            self.logger.warning(
                'JupyterExcel: notebook %s kernelspec %s has no matching %s execution profile; '
                'using default profile %s (kernel %s). '
                'This warning will not repeat for this routing decision during this server session.',
                path, kernel, language, profile, selected_kernel)
        return name


def resolve_profile(function, notebook, profiles, defaults, legacy_python=False, *, include_fallback=False):
    fallback = None
    language = notebook_language(notebook)
    name = function.execution_profile or notebook_profile(notebook)
    if name is None and language == 'python' and legacy_python:
        name = 'python-default'
    kernel_name = notebook.get('metadata', {}).get('kernelspec', {}).get('name')
    if name is None and kernel_name:
        matches = [name for name, p in profiles.items() if p['kernel_name'] == kernel_name and p['language'] == language]
        if len(matches) == 1:
            name = matches[0]
        elif defaults.get(language) in matches:
            name = defaults[language]
        elif matches:
            raise ValueError('No unambiguous execution profile for kernelspec ' + kernel_name + '. Configure or explicitly select a profile.')
        else:
            name = defaults.get(language)
            if name in profiles and profiles[name]['enabled'] and profiles[name]['language'] == language:
                fallback = (getattr(function, 'notebook', '<unknown>'), kernel_name,
                            language, name, profiles[name]['kernel_name'])
    name = name or defaults.get(language)
    if name not in profiles:
        raise ValueError('Unknown execution profile: ' + str(name))
    profile = profiles[name]
    if not profile['enabled']:
        raise ValueError('Execution profile is disabled: ' + name)
    if profile['language'] != language:
        raise ValueError('Execution profile ' + name + ' does not match notebook language ' + language)
    return (name, fallback) if include_fallback else name
