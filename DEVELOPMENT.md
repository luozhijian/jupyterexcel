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

GET: `/Excel/ADD?token=<token>&inputs=%5B3%2C4%5D`

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
function-list task pane is retained; ribbon and task-pane redesign is deferred.

Output is `<jupyter --data-dir>/excel-addin/`, with a username subfolder on Hub.
Unsafe username path characters are percent-encoded. Complete batches live in
`versions/<YYMDHmmss>/`; `current.json` points to the latest batch. The output root also contains manifest.xml, functions.json, HTML and versioned scripts for a separate static web server. Older versions remain available for cached
manifests. Retention cleanup is deferred. Colliding timestamps wait for the next
local-clock second. Generation failures retain the previous published batch.

### Runtime Excel authentication

Generated code supports an optional `globalThis.jupyterExcelAuth` async callback
returning `{token, hub}`. The caller supplies this at runtime; tokens are never
written into generated files. Without it, same-origin authenticated cookies are
used, with the XSRF header when available. Token-entry UI and credential storage
are deferred with task-pane design. Hub worksheet calls require token headers.
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

Edit `jupyterexcel/addin_template/functions-runtime.js` for shared request and
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
