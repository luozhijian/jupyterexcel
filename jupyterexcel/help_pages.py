"""Create editable function documentation without overwriting existing pages."""
import re
from html import escape

from .metadata import validate_function_name


def ensure_help_pages(root, templates, entries, namespace, functions):
    directory = root / 'help' / 'functions'
    directory.mkdir(parents=True, exist_ok=True)
    defaults = {f.function_id: {p.name: p.default for p in f.parameters}
                for f in functions if f.kind == 'jupyter'}
    template = None
    for entry in entries:
        function_id = validate_function_name(entry['id'])
        path = directory / (function_id + '.html')
        if path.exists():
            continue
        if template is None:
            template = (templates / 'help_template.html').read_text(encoding='utf-8')
        qualified = namespace + '.' + entry['name']
        arguments, rows = [], []
        for parameter in entry.get('parameters', []):
            name = parameter['name']
            argument = name + (', ...' if parameter.get('repeating') else '')
            arguments.append('[' + argument + ']' if parameter.get('optional') else argument)
            details = ['Optional.' if parameter.get('optional') else 'Required.',
                       'Type: ' + parameter.get('type', 'any') + '.',
                       'Dimensions: ' + parameter.get('dimensionality', 'scalar') + '.']
            if parameter.get('repeating'):
                details.append('Repeating argument; accepts additional values.')
            default = defaults.get(function_id, {}).get(name)
            if default is not None:
                details.append('Python default: ' + default + '.')
            description = parameter.get('description', '')
            if description and description != name:
                details.append(description)
            rows.append('<li><strong>' + escape(name) + '</strong> — ' +
                        escape(' '.join(details)) + '</li>')
        values = {
            'FUNCTION_NAME': escape(entry['name']),
            'QUALIFIED_NAME': escape(qualified),
            'DESCRIPTION': escape(entry.get('description', '')),
            'SYNTAX': escape('=' + qualified + '(' + ', '.join(arguments) + ')'),
            'ARGUMENTS': '<ul>' + ''.join(rows) + '</ul>' if rows else '<p>This function takes no arguments.</p>',
        }
        # One substitution pass prevents notebook text from becoming template markup.
        page = re.sub(r'\{\{([A-Z_]+)\}\}', lambda m: values.get(m[1], m[0]), template)
        try:
            # Exclusive creation also preserves a file created by another writer.
            with path.open('x', encoding='utf-8') as output:
                output.write(page)
        except FileExistsError:
            pass
