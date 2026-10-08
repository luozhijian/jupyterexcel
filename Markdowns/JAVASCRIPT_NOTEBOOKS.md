# JavaScript Notebook Exports

See [Execution profiles](EXECUTION_PROFILES.md) for `@executionProfile`,
per-environment kernel pools, capacity limits, and notebook isolation.

JupyterExcel discovers named top-level JavaScript function declarations in saved
`.ipynb` notebooks whose kernel/language metadata identifies JavaScript, TypeScript,
or Deno. The initial version accepts JavaScript syntax, not TypeScript annotations.
Discovery parses source; it does not execute notebook cells.

## Setup

Install Node.js 22 or newer on the Jupyter server PATH for the bundled static
parser. No npm installation is needed by package users. For server execution,
install Deno and register its Jupyter kernel in the environment running Jupyter:

```sh
deno jupyter --install
```

Select the Deno kernel for the notebook. Save it in a folder included by the
project's `discovery.include` setting. Save to generate assets, then reload the
Excel add-in. Changes to the exported signatures may require Excel's normal
custom-function metadata refresh/re-sideload workflow.

## Worksheet Function

```javascript
/**
 * Adds two numbers.
 * @excelFunction JS_ADD
 * @execution local
 * @param {number} a First number.
 * @param {number} [b=0] Second number.
 * @returns {number} Sum.
 * @example =Jupyter.JS_ADD(3, 5)
 */
function add(a, b = 0) {
  return a + b;
}
```

This publishes a worksheet formula and generated help, without an input form in
Notebook Actions. Only ribbon actions appear in the action dropdown. The
namespace (`Jupyter` above) follows `addin.namespace`.

## Ribbon Action

```javascript
/**
 * Formats a greeting on the server.
 * @ribbonFunction JS_GREET
 * @label Greeting
 * @buttonText Say Hello
 * @execution server
 * @param {string} name Recipient.
 * @returns {Promise<string>} Greeting text.
 * @remarks Requires the notebook server connection.
 * @see JS_ADD
 */
async function greet(name) {
  return "Hello " + name;
}
```

Use the existing Notebook Actions ribbon command to open the form. Individual
exports do not add dedicated manifest ribbon buttons. Ribbon actions never appear
in worksheet custom-function metadata. Their return value is previewed; writing
it to a worksheet uses the existing explicit destination/write workflow.

## Metadata

- `@excelFunction ID` / `@ribbonFunction ID`: explicit export. Snake-case aliases
  `@jupyter_function` / `@ribbon_function` are accepted. IDs must be unique across
  Python and JavaScript exports, compared case-insensitively.
- `@execution local|server`: required. Never silently falls back between runtimes.
- `@executionProfile name`: optional server environment/pool selection.
- Opening paragraph or `@description`: function description.
- `@param {type} name Description`: one entry per parameter, in declaration order.
- `@param {type} [name=value]`: optional input; its scalar literal default must
  agree with the JavaScript declaration. Omitted arguments use the code default.
- `@returns {type} Description`: required; `Promise<type>` is accepted.
- `@label`, `@buttonText`: form title and submit text; defaults are export ID and
  Run (actions) or Calculate (formulas).
- `@remarks`, `@sideEffects`, repeatable `@example`, and `@see`: generated help.
  `@see` accepts an exported ID or HTTP(S) URL. Unknown IDs fail publication.

Supported types are `number`, `string`, `boolean`, and homogeneous rectangular
2D arrays such as `number[][]`. Numbers must be finite. Matrices must contain
1-5000 cells. Objects, dates, null cells, rest/destructured parameters, and custom
widget tags are not supported in this version. Empty strings, zero, and false are
preserved. Literal matrix inputs use JSON text in the form.

## Execution and Dependencies

### Create Sankey Example

`JavaScriptExports.ipynb` exports `CREATE_SANKEY` as a local ribbon action.
Select Create Sankey in Notebook Actions, click the source input and select a
range including `Source`, `Target`, and `Value` headers. Then click the target
input and select a single cell. Click Create Sankey to insert the rendered image
with its top-left corner at that cell. Source and target can be on different sheets.

Example input:

| Source | Target | Value |
| --- | --- | ---: |
| Revenue | Operations | 60 |
| Revenue | Marketing | 25 |
| Revenue | Profit | 15 |
| Operations | Payroll | 40 |
| Operations | Infrastructure | 20 |

Requires ExcelApi 1.9. Supports up to 500 flow rows, 1503 selected cells, and 40
nodes. Values must be positive finite numbers. Labels are trimmed, case-sensitive,
and at most 60 characters. Duplicate flows are summed; cycles/self-links fail
before workbook changes. The PNG is a snapshot, not a native editable chart.
Edit cells and rerun to refresh. At the same target, only images carrying this
action's ownership marker are replaced; other shapes and cell contents remain.
Keep the target outside your data area so the floating image does not cover it.

The notebook calls the bundled `JupyterExcelCharts.createSankey` helper. The
version-pinned d3-sankey library and canvas renderer execute in the add-in with
no CDN or server execution request. Library licenses are shipped with the assets.
Build the helper with `npm ci` and `npm run build` in `tools/sankey`.

`@rangeInput parameterName` and `@cellInput parameterName` create selection controls
for required string parameters on local ribbon functions. The string contains a
serialized worksheet reference (sheet ID, zero-based row/column, rows/columns),
not the range values. This preserves worksheet identity across selection changes.

### Create Gantt Example

The top-level `JavaScriptExports.ipynb` contains one self-contained `CREATE_GANTT`
code cell. It runs locally from Notebook Actions, not as a worksheet formula.
Enter a range including headers, such as `A1:D7` on the active worksheet or
`'Project Plan'!A1:D7`. No Excel table is needed. Include `Task`, `Start`, `Finish`,
and `Progress` columns. Dates must be numeric Excel
dates, not text; progress must be numeric 0-1, normally formatted as a percentage.
The function supports 1-200 tasks and a daily timeline of at most 366 days.

Save the notebook, regenerate/reload the add-in, select Create Gantt, and run it.
Each run creates a new uniquely named worksheet. Green indicates completed days,
blue remaining days, gray weekends outside task bars, and an amber header marks
today. Calendar days, including weekends, count toward task duration and progress.
Nonzero partial days round up in the progress display.

Task details are linked to the source cells using absolute formulas. Editing existing dates
and progress updates conditional formatting after Excel recalculates. Rerun after
adding/removing tasks or extending dates beyond the original timeline. The source
range is not changed. Errors trigger best-effort deletion of the newly created
sheet; if cleanup fails, the error names that sheet. Workbook protection and host
errors may prevent creation. Requires ExcelApi 1.7 or later.

The conditional-format and freeze-pane APIs follow Microsoft's references:
[Conditional formatting](https://learn.microsoft.com/en-us/office/dev/add-ins/excel/excel-add-ins-conditional-formatting)
and [freeze panes](https://learn.microsoft.com/en-us/javascript/api/excel/excel.worksheetfreezepanes).

### Local and Server Execution

Local functions are embedded as JavaScript source in the add-in bundle, with
their parameter/result contract. They must be self-contained; references to
other cells, imports, Deno, Node, or browser APIs are rejected for now.
Local ribbon functions may reference `Excel` and `Office` to manipulate workbooks;
worksheet functions cannot. Only publish trusted notebook code: this dependency
check is not a security sandbox. Add `@output status` to a local ribbon function
returning a string to display a completion message without range-write controls.
Standard calculation globals (Math, JSON, Array, etc.) are supported. Functions
may contain their own nested helpers. Keep local work short: synchronous work
runs on the add-in thread and cannot be interrupted by a timeout.

Server functions use notebook-isolated workers in the selected execution profile.
The current JavaScript execution/result protocol supports Deno. Saved code cells
initialize that kernel once, in notebook order, including imports and top-level
statements. Do not put destructive top-level operations in export notebooks.
Calls within a worker are serialized; workers and notebooks have separate state. The
interactive notebook's unsaved state is not shared. A saved source change retires
the old kernel on its next call. Explicit Save and Reload also retires it.

The request carries a source revision. A mismatched revision asks the user to
reload the add-in instead of executing newer server code under older metadata.
Server execution uses the existing authenticated endpoint and profile timeout;
a timed-out executing kernel is retired, and actions are never automatically
retried. Shutdown closes managed kernels. The status display includes each
execution profile's kernels and queue.

Only publish trusted notebook code: local exports run with add-in privileges,
and Deno notebook kernels have access to their server environment. Client calls
send registered IDs and JSON arguments, not arbitrary source code.

## Help and Compatibility

`help/index.html` is searchable and links to generated reference pages under
`help/generated/`. The pages contain descriptions, usage, parameters, defaults,
result details, execution mode, examples, related links, and source revision.
Text is escaped and examples are never executed. The form's Help link and
JavaScript worksheet metadata point to these pages.

Existing Python decorators remain supported, including their description, label,
and button_text fields. Existing editable `help/functions/` pages are preserved.
Generated reference pages are rebuilt with assets; edit notebook documentation,
not the generated files. No automatic dependency bundling, dedicated ribbon
buttons, slider/choice annotations, or automatic retries are included.

## Parser Maintenance

The bundled parser uses Acorn, Doctrine, and eslint-scope. Its reproducible build
is in `tools/jsdoc-parser`; run `npm ci` then `npm run build` there when changing
`jupyterexcel/jsdoc_parser.cjs`. Third-party licenses are shipped with the bundle.
