"""Literal action schemas shared by notebook discovery and kernel invocation."""
import copy
import math
import re

MAX_CELLS = 5000


def action_schema(name, inputs, output=None, label=None, button_text='Run', description=''):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9.]+', name):
        raise ValueError('Action name must contain only ASCII letters, digits, and periods.')
    if not isinstance(inputs, dict):
        raise ValueError('Action inputs must be a literal dictionary keyed by parameter name.')
    fields = []
    for key, raw in inputs.items():
        if not isinstance(key, str) or not key.isidentifier() or not isinstance(raw, dict):
            raise ValueError('Invalid action parameter.')
        field = copy.deepcopy(raw)
        if set(field) - {'source', 'type', 'read', 'label', 'default', 'choices', 'repeatable', 'max_cells'}:
            raise ValueError('Unsupported action input property: ' + key)
        field.update(name=key, source=field.get('source', 'value'), type=field.get('type', 'string'))
        if field['source'] not in {'value', 'cell', 'range'}:
            raise ValueError('Unsupported action source.')
        if field['type'] not in {'string', 'text', 'number', 'boolean', 'choice', 'matrix'}:
            raise ValueError('Unsupported action input type.')
        if not isinstance(field.get('repeatable', False), bool):
            raise ValueError('repeatable must be boolean.')
        if field['source'] != 'value':
            props = field.get('read', ['values'])
            allowed = {'values', 'format.fillColors'}
            props = ['format.fillColors' if p in ('fillColor', 'fillColors') else p for p in props]
            if 'values' not in props:
                raise ValueError('Excel inputs must include values.')
            if not isinstance(props, list) or not props or len(set(props)) != len(props) or not set(props) <= allowed:
                raise ValueError('Unsupported Excel read properties.')
            field['read'] = props
            limit = field.get('max_cells', MAX_CELLS)
            if type(limit) is not int or not 1 <= limit <= MAX_CELLS:
                raise ValueError('max_cells must be between 1 and 5000.')
            field['max_cells'] = limit
            if field['source'] == 'range' and field['type'] != 'matrix':
                raise ValueError('Range inputs must use type matrix.')
        elif 'read' in field:
            raise ValueError('Value inputs do not read workbook properties.')
        if field['type'] == 'choice':
            choices = field.get('choices')
            if not isinstance(choices, list) or not choices or not all(isinstance(c, str) for c in choices):
                raise ValueError('Choices must be nonempty strings.')
        fields.append(field)
    output = copy.deepcopy(output or {'type': 'matrix', 'destinations': ['taskpane', 'range']})
    if set(output) - {'type', 'destinations', 'default'}:
        raise ValueError('Unsupported output property.')
    if output.get('type') not in {'number', 'string', 'text', 'boolean', 'matrix'}:
        raise ValueError('Unsupported output type.')
    destinations = output.setdefault('destinations', ['taskpane'])
    if isinstance(destinations, str):
        destinations = output['destinations'] = [destinations]
    if not isinstance(destinations, list) or not destinations or not set(destinations) <= {'taskpane', 'range', 'popup'}:
        raise ValueError('Unsupported output destination.')
    output.setdefault('default', 'taskpane' if 'taskpane' in destinations else destinations[0])
    if output['default'] not in destinations:
        raise ValueError('Default output destination must be allowed.')
    if not all(isinstance(v, str) and v.strip() for v in (label or name, button_text)) or not isinstance(description, str):
        raise ValueError('Action labels and button text must be strings.')
    return dict(id=name.upper(), label=label or name, button_text=button_text,
                description=description, inputs=fields, output=output)


def matrix(value):
    if not isinstance(value, list) or not value or not isinstance(value[0], list) or not value[0]:
        raise ValueError('Expected a nonempty matrix.')
    width = len(value[0])
    if any(not isinstance(row, list) or len(row) != width for row in value) or len(value)*width > MAX_CELLS:
        raise ValueError('Matrix must be rectangular with at most 5000 cells.')
    return len(value), width


def validate_value(value, kind):
    if kind == 'number' and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError('Expected a finite number.')
    if kind in ('text', 'string', 'choice') and not isinstance(value, str):
        raise ValueError('Expected text.')
    if kind == 'boolean' and type(value) is not bool:
        raise ValueError('Expected a boolean.')
    if kind == 'matrix':
        matrix(value)
        for row in value:
            for cell in row:
                if cell is not None and type(cell) not in (str, int, float, bool):
                    raise ValueError('Matrix cells must be scalar values.')
                if type(cell) in (int, float) and not math.isfinite(cell):
                    raise ValueError('Matrix numbers must be finite.')


def validate_inputs(schema, values):
    if not isinstance(values, list) or len(values) != len(schema['inputs']):
        raise ValueError('Supply one argument for each declared action input.')
    for field, supplied in zip(schema['inputs'], values):
        entries = supplied if field.get('repeatable') else [supplied]
        if not isinstance(entries, list) or not 1 <= len(entries) <= 50:
            raise ValueError('Repeatable inputs require 1 to 50 entries.')
        for value in entries:
            if field['source'] == 'value':
                validate_value(value, field['type'])
                if field['type'] == 'choice' and value not in field['choices']:
                    raise ValueError('Unknown choice.')
                continue
            validate_block(value, input_block=True)
            expected = {'values', 'format'} if 'format.fillColors' in field['read'] else {'values'}
            if set(value) != expected or ('format' in value and set(value['format']) != {'fillColors'}):
                raise ValueError('Excel input properties do not match the action schema.')
            rows, columns = matrix(value['values'])
            if rows * columns > field['max_cells']:
                raise ValueError('Excel input exceeds the cell limit.')
            if field['source'] == 'cell':
                if (rows, columns) != (1, 1):
                    raise ValueError('Cell inputs require a 1 by 1 matrix.')
                if field['type'] != 'matrix':
                    validate_value(value['values'][0][0], field['type'])


def validate_block(block, input_block=False):
    if not isinstance(block, dict) or 'values' not in block or set(block) - {'values', 'format'}:
        raise ValueError('Cell data must contain values and optional format.')
    validate_value(block['values'], 'matrix')
    if 'format' in block:
        formatting = block['format']
        if not isinstance(formatting, dict) or set(formatting) - {'fillColors'}:
            raise ValueError('Only fillColors formatting is supported.')
        if 'fillColors' in formatting:
            colors = formatting['fillColors']
            if matrix(colors) != matrix(block['values']):
                raise ValueError('Fill colors must match values dimensions.')
            for row in colors:
                for color in row:
                    if color is None and not input_block:
                        continue
                    if not isinstance(color, str) or (color != '' and not re.fullmatch(r'#[0-9A-Fa-f]{6}', color)):
                        raise ValueError('Fill colors must be #RRGGBB or empty string; output also permits null to preserve fill.')
    return block


def validate_result(schema, result):
    if not isinstance(result, dict) or 'result' not in result or set(result) - {'result', 'columns', 'updates'}:
        raise ValueError('Return {result: ...}, optionally with columns and updates.')
    if schema['output']['type'] == 'matrix' and isinstance(result['result'], dict):
        validate_block(result['result'])
        if 'columns' in result:
            raise ValueError('Include headers in values when returning a formatted block.')
    else:
        validate_value(result['result'], schema['output']['type'])
    if 'columns' in result:
        if schema['output']['type'] != 'matrix' or not isinstance(result['columns'], list) or not all(isinstance(c, str) for c in result['columns']) or len(result['columns']) != len(result['result'][0]):
            raise ValueError('Columns must match the result matrix width.')
    updates = result.get('updates', {})
    if not isinstance(updates, dict):
        raise ValueError('Updates must be keyed by input name.')
    fields = {f['name']: f for f in schema['inputs']}
    for name, update in updates.items():
        field = fields.get(name)
        if not field or field['source'] == 'value' or field.get('repeatable'):
            raise ValueError('Updates must target a non-repeating Excel input.')
        validate_block(update)
    return result
