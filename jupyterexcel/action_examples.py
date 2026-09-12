"""Calculation used by examples/SumGroupByColor.ipynb; no Excel access here."""
import math
from .actions import matrix


def group_sum_by_color(data):
    values, colors = data['values'], data['format']['fillColors']
    if matrix(values) != matrix(colors):
        raise ValueError('Values and fill colors must have identical dimensions.')
    groups = {}
    for row, color_row in zip(values, colors):
        for value, color in zip(row, color_row):
            if type(value) not in (int, float):
                continue
            if not math.isfinite(value):
                raise ValueError('Cannot sum a non-finite number.')
            key = color.upper()
            count, total = groups.get(key, (0, 0))
            groups[key] = count+1, total+value
    if not groups:
        raise ValueError('The selected range contains no numeric cells.')
    rows = [[groups[key][0], groups[key][1]]
            for key in sorted(groups, key=lambda color: (color == '', color))]
    return {'result': {'values': [['Count', 'Sum']] + rows,
                       'format': {'fillColors': [[None, None]] +
                                  [[key, key] for key in sorted(groups, key=lambda color: (color == '', color))]}}}
