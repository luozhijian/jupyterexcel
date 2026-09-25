"""Shared validation for explicit Office worksheet metadata."""
from collections.abc import Mapping
import re


def validate_function_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9._]+', name):
        raise ValueError('Worksheet function names must contain only ASCII letters, digits, periods, or underscores.')
    return name


TYPES = ('any', 'number', 'string', 'boolean')
DIMENSIONALITIES = ('scalar', 'matrix')


def validate_metadata(parameter_names, parameter_types, parameter_dimensionality,
                      result_type, result_dimensionality):
    for label, mapping, allowed in (
        ('parameter_types', parameter_types, TYPES),
        ('parameter_dimensionality', parameter_dimensionality, DIMENSIONALITIES),
    ):
        if mapping is None:
            continue
        if not isinstance(mapping, Mapping):
            raise ValueError(label + ' must be a mapping of parameter names to values.')
        for name, value in mapping.items():
            if name not in parameter_names:
                raise ValueError(label + ': unknown parameter ' + str(name))
            if value not in allowed:
                raise ValueError(label + ': ' + str(name) + ' must be one of ' + ', '.join(allowed))
    if result_type not in TYPES:
        raise ValueError('result_type must be one of ' + ', '.join(TYPES))
    if result_dimensionality not in DIMENSIONALITIES:
        raise ValueError('result_dimensionality must be scalar or matrix')
