# Notebook Actions

The existing shared task pane contains Notebook Actions. Actions are discovered statically from literal `@ribbon_function` metadata, separately from worksheet functions. The dropdown refreshes from generated `actions.json`; it does not run notebook code. Legacy positional `ribbon_function(name, return_value, **mappings)` remains available for older clients but is not executable in this pane.

## Try the demo

1. Restart Jupyter Server using the updated package.
2. Copy `examples/SumGroupByColor.ipynb` into the server's visible notebook root and save it. This regenerates the static assets at your configured asset directory.
3. Restart the existing managed JupyterExcel kernel if it was initialized before the action was added. The next request loads both worksheet-export and action-export notebooks in sorted path/cell order.
4. Reload or re-sideload the generated manifest in Excel to add the Notebook Actions button. Use your existing token dialog to supply a valid token.
5. Open the shared task pane and select Sum Group by Color. Click Data range, then select a contiguous range in Excel with the mouse. Click Starting Cell and select one output cell, then Calculate. Only the active field follows mouse selection; Calculate stops selection tracking.
6. Read the result table. Choose a single output cell outside the inputs and Write to cells to export the table, including column headings. Occupied destinations require confirmation. The original cell colors are not modified.

The demo groups the same cells it sums. Manual solid fill colors are normalized to uppercase #RRGGBB; an empty string means No fill and differs from white. Text, blanks and booleans are ignored. Hidden/filtered cells are included. Excel errors, conditional formatting, patterned fills and unsupported hosts produce explicit errors. No numeric cells produces a clear message. Fill reading requires ExcelApi 1.9. The maximum selection is 5000 cells; fields can lower that limit.

## Define another action

```python
from jupyterexcel import ribbon_function

@ribbon_function(
    name="MULTIPLY",
    label="Multiply",
    inputs={
        "a": {"source": "value", "type": "number"},
        "b": {"source": "value", "type": "number", "default": 2},
    },
    output={"type": "number", "destinations": ["taskpane", "range"]},
)
def multiply(a, b):
    return {"result": a * b}
```

`button_text` defaults to Run. All input definitions must match positional function parameters in order; zero, one, or multiple parameters work. Inputs are required; defaults prefill controls. Python optional defaults are not inferred into controls. For variable counts use `repeatable: True`: Add input/Remove produces a list passed as one Python argument (1â€“50 entries), not Python `*args`.

Input sources are value, cell, and range. Value types are number, string/text, boolean, choice, and matrix (JSON table input). A literal text A1 stays text. Cell/range inputs capture worksheet ID, bounds, and address. Click the field, then select with the mouse; switching fields changes which input follows selection. Starting Cell is available before calculation for actions allowing range output and accepts exactly one cell. Selection tracking requires ExcelApi 1.2.

Use `read: ["values", "format.fillColors"]` to request colors, or `read: ["values"]` for values only. Older metadata names fillColor/fillColors normalize to format.fillColors. Both cell and range inputs are blocks: `{"values": [[10]], "format": {"fillColors": [["#FFFF00"]]}}`. A cell is a 1 by 1 matrix. Each formatting matrix matches values dimensions. Input fills are hex colors or empty strings (no fill); a failed color read is an error, never null. Values are always included.

The pane generates any number of controls from metadata; it has no special SumGroupByColor logic. Primitive value inputs, selection capture, batch reading, execution and rendering are shared.

## Return contract

Return a scalar with `{"result": 40}`, or use the same cell block as input:

```python
return {"result": {
    "values": [["Color", "Count", "Sum"], ["Yellow", 2, 40]],
    "format": {"fillColors": [[None, None, None], ["#FFFF00", None, None]]}
}}
```

Headers are a row in values, keeping formatting aligned. On output, hex applies a fill, an empty string clears the fill, and None preserves the destination fill. Omitted format writes values only. Matrices must be rectangular, scalar-only and at most 5000 cells. The pane and popup display supplied fills, and Write to cells applies values and fills beginning at Starting Cell. Empty destinations may receive the returned fills without confirmation. Conditional formatting may override the visible destination color and is not modified.

Existing unformatted matrix results and columns remain supported for compatibility. Output destinations are taskpane, range, and popup; popup is a modal within the pane. When range is the default output, Calculate automatically writes to Starting Cell if the entire destination contains no values or formulas. Occupied destinations show a confirmation with the first five occupied cells and their proposed replacement values. Cancelling keeps the result available; Write to cells retries only the write, without recalculating Python. The returned dimensions determine the output rectangle.

Optional updates map a non-repeating cell/range input name to the same values/format block. Dimensions must match the captured selection and updates require confirmation. No arbitrary remote Excel commands execute. Formula-like strings are written as text. Workbook changes can make results stale; run again before writing. Change detection is best effort on older hosts and newly added sheets. Values and formatting are written in batches, not as an atomic transaction; a host failure can leave partial writes, and no retry is automatic.

## Server execution

POST `<server-base>/Excel/<function-id>` with Authorization token and a JSON positional argument array. GET does not execute actions. This uses the same authentication, Hub owner checks, size limit, server managers and serialized shared kernel as worksheet execution. POST resolves decorated worksheet functions or actions by unique ID. IDs must be unique across both categories. GET retains legacy worksheet calls but cannot execute actions. UI catalogs are retrieved with GET from generated actions.json/functions.json without executing notebooks. Inputs and result envelopes are validated in the kernel. User-supplied strings remain JSON data, never Python code.

No automatic retries occur. A timeout may leave Python running. A request timeout in the pane is 120 seconds; the server execution timeout remains configurable. Saving a notebook refreshes metadata, not the live kernel definitions. Action functions must return synchronously and JSON-serializable values. Notebook initialization still executes all code cells and is intended for trusted notebooks.

## Validation

Run `python -m unittest discover -s tests -v` and `node --test tests/test_actions_client.cjs tests/test_client_runtime.cjs tests/test_dialog_command.cjs`. Real Excel validation is still required for selection, fill reads, UI dialogs and workbook writes. No credentials are embedded in generated resources.

SumGroupByColor returns Count and Sum only. Both cells in each group row receive that group's background color; no-fill groups clear both backgrounds.
