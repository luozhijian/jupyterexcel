# JupyterExcel Development

## Requirements

- Windows, macOS, or Linux for the Python server.
- Python 3 with Jupyter Server or classic Jupyter Notebook.
- `jupyter_client`, Tornado, and ZeroMQ dependencies supplied by Jupyter.
- Excel with Office Add-in support for the generated Office.js client.
- HTTPS and a trusted certificate for Office.js sideloading.

## Editable installation

From the repository root:

```powershell
python -m pip install -e .
```

Enable the extension using the command supported by the installed Jupyter generation:

```powershell
jupyter server extension enable --py jupyterexcel
```

For classic Notebook installations:

```powershell
jupyter serverextension enable --py jupyterexcel
```

Start Jupyter from a directory whose notebooks should be visible to Excel. Notebook discovery is limited to the active Jupyter contents root.

## Rewritten worksheet API

Run the notebook definition cells before calling an exported `@jupyter_function`.
The endpoint is now `/Excel/<exported-id>`, not a notebook path. This replaces the
legacy notebook-path, form-encoded transport and automatic notebook execution.

GET: `/Excel/ADD?token=<token>&params=%5B3%2C4%5D`

POST: `/Excel/ADD?token=<token>`, Content-Type `application/json`, body `[3, 4]`.
The top-level list is always unpacked. Pass `[[3, 4]]` for one list argument.
Responses are `{"ok": true, "result": ...}` or
`{"ok": false, "error": {"code": "...", "message": "..."}}`.
Only decorated worksheet functions already defined in the selected kernel are callable.
Results must be JSON serializable. Async functions are not supported in this version.

Single-user mode selects the first kernel. Hub mode requires a validated token
header and the authenticated user's own server, then selects its first idle,
unreserved kernel. Another user's server is rejected, including delegated access.
A missing or busy kernel returns 503. The timeout defaults to 30 seconds; set
`JUPYTEREXCEL_EXECUTION_TIMEOUT` to override it. A timeout does not interrupt the
kernel, since interruption could affect notebook work.

### Generated assets and templates

Assets are built at startup and after successful saves. Jupyter Server contents
events also trigger regeneration after rename/delete/copy. Older classic Notebook
managers without events refresh on the next save or startup.

Packaged source templates live in `jupyterexcel/addin_template`. The original
repository-root `addin_template` files are preserved. The supplied functions.js
sample registrations are replaced by notebook registrations. The existing
function list is retained inside the merged debug-log task pane. Notebook ribbon execution remains deferred.

Output is `<jupyter --data-dir>/excel-addin/`, with a username subfolder on Hub.
Unsafe username path characters are percent-encoded. Complete batches live in
`versions/<YYMDHmmss>/`; `current.json` points to the latest batch. The output root also contains manifest.xml, functions.json, HTML and versioned scripts for a separate static web server. Older versions remain available for cached
manifests. Retention cleanup is deferred. Colliding timestamps wait for the next
local-clock second. Generation failures retain the previous published batch.

### Runtime Excel authentication

Generated code supports an optional `globalThis.jupyterExcelAuth` async callback
returning `{token, hub}`. The caller supplies this at runtime; tokens are never
written into generated files. Without it, same-origin authenticated cookies are
used, with the XSRF header when available. The merged Input Access Token dialog supplies credentials through shared OfficeRuntime.storage. Hub worksheet calls require token headers.
Office assets are served without tokens by your separate static web server. Jupyter registers only the authenticated /Excel/<function-id> API; it does not serve Office assets.

## Static web server configuration

Map your public web server to the `excel-addin` output directory. Files are published
at its root; a Hub user gets a username subdirectory. The public server needs no
Jupyter token for these files.

The generator does not need your static website's address. HTML uses relative
script and stylesheet references. The manifest retains the absolute URLs supplied
in `jupyterexcel/addin_template/manifest.xml`, updating the generated JavaScript
filename only. Configure those template URLs for your website when deploying;
Office manifest URLs are not inferred from the Jupyter server.

Serve the output root, which contains the manifest, HTML, metadata, and versioned
scripts. In Hub, serve each user's output subfolder at the paths configured in that
user's manifest template. No username is automatically inserted into manifest URLs.
Archived batches remain under `versions/`, but the stable manifest references the
published root files. Configure suitable cache revalidation for the manifest,
HTML, and functions.json on your web server.

Public asset downloads require no token; calls back to Jupyter still require
authentication. `JUPYTEREXCEL_PUBLIC_URL` still controls the Jupyter API address,
not the static website. Cross-origin API access remains subject to Jupyter's CORS
configuration; the extension does not disable authentication or CORS.

## Public add-in URL

If Excel should use the Jupyter server's own origin, start Jupyter with HTTPS and let JupyterExcel derive the URL.

When a reverse proxy, fixed development port, or other public origin is required, set:

```powershell
$env:JUPYTEREXCEL_PUBLIC_URL = "https://localhost:3000"
```

Then start Jupyter in the same terminal. The value must be an origin and optional base path reachable from the machine running Excel. Do not include authentication tokens.

## Creating a worksheet function

Add a decorated function to any visible notebook:

```python
from jupyterexcel import jupyter_function

@jupyter_function(
    name="ADD",
    description="Add two numbers",
    parameter_types={"a": "number", "b": "number"},
    result_type="number",
)
def add(a, b=0):
    return a + b
```

Excel exposes it under the manifest namespace, currently `JUPYTER`, as `JUPYTER.ADD`.

Function IDs must be unique across all notebooks visible to that Jupyter server. Prefer a stable explicit `name` for functions that users may save in workbooks.

## Generated endpoints

After startup, inspect these URLs in a browser:

```text
https://<host>:<port>/manifest.xml
https://<host>:<port>/public/functions.json
https://<host>:<port>/public/functions.js
https://<host>:<port>/public/functions.html
https://<host>:<port>/commands.html
https://<host>:<port>/taskpane.html
```

The `/jupyterexcel/...` forms remain compatibility aliases. The startup log reports the generated manifest URL and the number of discovered worksheet functions.

## Sideloading and cache behavior

Sideload the generated `/manifest.xml` using the method appropriate for the installed Excel version and organization policy. The certificate must be trusted before Excel loads the resources.

Excel caches custom-function metadata. After adding, removing, or renaming decorators:

1. Save the notebook.
2. Confirm the updated function appears in `/public/functions.json`.
3. Restart Excel or clear its Office add-in cache.
4. Reload or sideload the manifest if necessary.

## Automated tests

Run the unit tests:

```powershell
python -m unittest discover -s tests -v
```

Compile the Python modules:

```powershell
python -m py_compile jupyterexcel\utils.py jupyterexcel\office_addin.py jupyterexcel\server_extension.py
```

Check patch hygiene:

```powershell
git diff --check
```

The focused tests cover decorator discovery, nested notebook paths, metadata generation, JavaScript association, and XML parsing. They do not prove that Excel can authenticate to a live Jupyter kernel.

## Live integration checklist

For changes to transport or execution, verify at least:

- A number and a string argument.
- An optional argument omitted from the Excel formula.
- A two-dimensional array input or result.
- A nested notebook path.
- A Python exception rendered as a useful Excel error.
- Notebook edits updating assets without executing cells; rerun definition cells manually.
- Authentication from the Office.js runtime.

## Debugging

If the function is absent in Excel:

- Open `/public/functions.json` and confirm its ID and parameter metadata.
- Open `/public/functions.js` and confirm a matching `CustomFunctions.associate` call.
- Check for duplicate IDs during server startup.
- Clear Excel's add-in cache.

If the function returns an error:

- Inspect the browser/Office add-in console and Jupyter server log.
- Confirm the generated endpoint includes the exported function ID and correct server base URL.
- Open the notebook normally and ensure its kernel starts.
- Verify the HTTP response is valid JSON rather than Python dictionary text.

If Office resources do not load:

- Confirm every manifest URL is reachable from the Excel computer.
- Confirm the HTTPS certificate is trusted.
- Confirm `JUPYTEREXCEL_PUBLIC_URL` matches the proxy-facing origin.
- Check Jupyter authentication without placing credentials in generated files.

## Ribbon development

`@ribbon_function` discovery currently feeds the task-pane listing. Individual generated ribbon buttons and command handlers are not implemented yet. When adding them, update the manifest generator, command JavaScript, decorator metadata model, and integration tests together.

## JavaScript source templates

Edit `jupyterexcel/addin_template/jupyter-runtime.js` for shared request and
runtime authentication logic. `functions.js` in the same folder is the bundle
template, with exactly one `{{FUNCTIONS_RUNTIME}}` and one
`{{FUNCTION_REGISTRATIONS}}` placeholder. Generation loads these files and emits
one complete `functions.<version>.js`; Excel does not need to load the helper
separately. Notebook registrations are generated by Python, while the shared
JavaScript remains editable as JavaScript. Custom template directories must
provide both files.

The packaged manifest template uses `{{FUNCTIONS_SCRIPT}}` for the versioned
script filename. Its website URLs remain those specified in the template.
Existing `setup.py` package-data patterns include these templates in pip packages.

## Merged Excel client

The editable templates under `jupyterexcel/addin_template` now include the tested
JupyterExcel debug-log task pane, CSS, token dialog, and access-token ribbon
command. The task pane also retains the notebook worksheet/ribbon listing. These
UI commands are separate from notebook `@ribbon_function` execution, which remains
deferred. The client sample ADD/SUM/CLOCK/INCREMENT/LOG registrations are not copied;
worksheet registrations still come exclusively from notebook metadata.

`jupyter-runtime.js` combines the shared logger and HTTP transport with no ES
module imports or DOM dependency. It is bundled into the generated functions
script; the UI pages load it separately with `jupyter-config.<version>.js`.
All local HTML scripts are explicitly referenced; webpack is not needed to use
the packaged templates. Manifest absolute URLs remain under template control.

The Input Access Token dialog sends the entered credential to its same-origin
Office command parent. The parent validates against the configured Jupyter API
(and checks the username on Hub), then saves it in OfficeRuntime.storage. Both
credentials and log settings are scoped by API base URL and Hub username. The
worksheet runtime reads this same storage, or uses the existing
`globalThis.jupyterExcelAuth` override. LocalStorage is used only for the UI's
expanded/collapsed preference, not authentication credentials. Office DialogApi
1.2 support is required for parent-to-dialog confirmation. Jupyter's CORS policy
must permit the actual add-in origin; the extension does not relax it.

Logging defaults to disabled / Normal. Enable it in Show Debug Log. Request logs
contain function name, argument count, HTTP status and elapsed time, not worksheet
values, results, tokens, full URLs, or raw exception text. The logger retains up to
200 entries and 200,000 characters and redacts credential-shaped fields. Clear,
pause, filter, copy, and export controls are carried over from the tested client.

Run JavaScript regression tests with `node --test tests/test_client_runtime.cjs`.
These simulate separate Office runtimes and storage; live Excel/Hub validation is
still required for actual Office dialog/storage support and deployment CORS.

## Parameter types and dimensions

`@jupyter_function` accepts `parameter_types`, `parameter_dimensionality`,
`result_type`, and `result_dimensionality`. Omitted types default to `any` and
omitted dimensions default to `scalar`, independently for every parameter and
for the result. Supported types: `any`, `number`, `string`, `boolean`.
Supported dimensions: `scalar`, `matrix` (a rectangular two-dimensional array).

```python
@jupyter_function(
    name="SCALE",
    parameter_types={"values": "number", "factor": "number"},
    parameter_dimensionality={"values": "matrix"},
    result_type="number",
    result_dimensionality="matrix",
)
def scale(values, factor=2):
    return [[value * factor for value in row] for row in values]
```

Excel receives explicit type and dimensionality in functions.json. Use literal
metadata values/dictionaries so static discovery can read them without executing
cells. Invalid metadata and unknown parameter names raise ValueError.
These declarations do not coerce or validate HTTP argument values at runtime.
Return nested Python lists for matrix results. Automatic DataFrame conversion
and Python annotation inference are not implemented.

Restart Jupyter after upgrading, rerun definition cells in the kernel, and save
the notebook to regenerate metadata. Reload the add-in if Excel caches an older
function signature.

## Override the asset output directory

Set the variable in the same PowerShell session before launching Jupyter:

```powershell
$env:JUPYTEREXCEL_ASSET_DIR = "C:\Websites\JupyterExcel\excel-addin"
jupyter lab
```

The value must be an absolute filesystem directory, not a URL. Standalone Jupyter
writes directly there; Hub appends its username subdirectory. When the variable
is unset, output remains `<jupyter-data-dir>/excel-addin/` (plus username on Hub).
An empty or relative setting is rejected. Missing directories are created during
generation; permission failures are reported without falling back elsewhere.
Changing this setting does not move existing output or configure your web server.

The two-argument notebook test continues to use its explicit output directory.
Programmatic `output_dir` overrides the environment; explicit `data_dir` retains
its existing data-directory behavior for tests. Normal server startup uses the
environment variable or Jupyter's default data directory.

GET requests require `params` for the JSON-encoded positional array. There is no
`inputs` compatibility alias. POST still accepts the JSON array directly as its body;
no object wrapper is required. Both methods return `params` for argument-format
error codes.

## Skip unchanged asset builds

Generation renders candidate content with a fixed version placeholder and hashes
the resulting files (including templates, icons, metadata, registrations and API
configuration). The fingerprint and published-file hashes are stored in
`current.json` only after successful publication. Notebook outputs and calculation
body edits do not change the fingerprint unless generated content changes.

Matching builds reuse the existing version, including after a server restart,
and leave unchanged public files untouched. Missing or modified public files are
restored from the verified archived batch without assigning a new timestamp.
If that archive is missing or damaged, a new batch is generated. An older
`current.json` without fingerprints causes one fresh build. Temporary candidates
are discarded on unchanged builds and failures. `generate()` returns True when a
new version is published and False when the current version is reused/repaired.

The current deployment requires JUPYTEREXCEL_ASSET_DIR (or an explicit test output
directory); the user's removal of the default data-directory fallback is retained.

## Managed shared kernel

Excel requests now create/reuse a console session named
`JupyterExcel - <username> - <number>` using the `python3` kernelspec.
Hub uses JUPYTERHUB_USER; standalone uses the operating-system username.
The label belongs to the running session, not the installed Python kernelspec.
Select this existing session/kernel in JupyterLab to debug its shared namespace.
Names are checked against active sessions, and replacements increment the number.
The actual kernel UUID is tracked separately; labels do not grant access.

On the first call, all code cells in notebooks containing @jupyter_function
exports execute in sorted notebook-path order. This includes imports and other
cell side effects. Notebooks without worksheet exports are not automatically run.
All loaded notebooks share globals. Custom load ordering remains deferred.
Initialization failures block calls until the kernel is restarted, avoiding
repeated partial execution. A timed-out operation may still be running.

Saves continue to generate assets without running cells. To load saved code
changes, restart the managed kernel; its next Excel call reloads the notebooks.
Manual edits in an attached notebook otherwise remain available for debugging.
Concurrent Excel requests serialize; an already busy managed kernel returns 503.
Shutdown/dead kernels are replaced on the next request. This implementation does
not adopt an arbitrary existing session based only on its display name.

Shared-server authorization has not changed: Hub Excel requests still require
the server owner's authenticated token. Team-member API delegation is deferred.
These details supersede the earlier first-kernel/manual-definition instructions.

## Repeating worksheet parameters

Python `*values` is exported as the final Office parameter with `repeating: true`.
Types and dimensionality still default to any/scalar. Use number/matrix to accept
multiple numeric ranges and individual numbers. Excel groups the repeated values
into one array; the generated bridge expands that group into Python positional
arguments, preserving each matrix. HTTP callers continue to send the positional
array directly, for example `[2, [[3,4]], 5]`. Keyword parameters after *values
are rejected. Blank/text handling is the Python function's responsibility.
Restart Jupyter Server, save to regenerate assets, and reload the Excel add-in
metadata after changing a parameter to repeating.

