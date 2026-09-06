# JupyterExcel Architecture

## Implemented rewrite

`ExcelModeHandler` now accepts GET `inputs` or a POST JSON array at
`/Excel/<function-id>`. `execution.py` selects kernels through the active server's
kernel manager, reserves each kernel during dispatch, and correlates replies by
message ID. It calls only decorated worksheet functions already in the selected
kernel; it never runs notebook cells automatically. See DEVELOPMENT.md for the
response contract and authentication setup.

`assets.py` performs asynchronous ContentsManager discovery and save-triggered
asset generation. It copies packaged templates into immutable timestamped batches,
then publishes files and a stable manifest at the data-directory output root. A separate public web server serves these assets without tokens; no Office asset routes are registered in Jupyter.
Previous batches remain available. The current ribbon listing and task pane are
preserved. Legacy notebook-path execution below describes the pre-rewrite design.

## Previous architecture (historical)

## Overview

JupyterExcel exposes Python functions defined in Jupyter notebooks to Excel. The current repository supports an older Excel/VBA client and a dynamically generated Office.js add-in surface.

```text
Notebook code cells
    |
    | static decorator discovery
    v
office_addin.py
    |-- manifest.xml
    |-- functions.json
    |-- functions.js
    |-- functions.html
    |-- commands.html
    `-- taskpane.html
             |
             | HTTPS request
             v
server_extension.py /Excel/<notebook-path>
             |
             | Jupyter session + kernel client
             v
Notebook kernel function call
             |
             `-- JSON-compatible result --> Excel
```

## Package responsibilities

### `jupyterexcel/utils.py`

Defines the notebook-facing decorators and runtime registries.

- `jupyter_function` marks a Python function as an Excel worksheet custom function. It records the Excel name, description, parameter metadata, optional arguments, and result type.
- `ribbon_function` records the older ribbon callback metadata, including argument mappings and a return target.
- Decorated Python functions remain normally callable inside the notebook.

### `jupyterexcel/office_addin.py`

Contains the static discovery and Office resource generation layer.

1. `discover_notebooks` walks the current Jupyter `ContentsManager`, including nested directories.
2. `scan_notebook` parses code cells with Python's AST and finds `jupyter_function` and `ribbon_function` decorators without executing notebooks.
3. `functions_metadata` generates Office custom-functions JSON for `jupyter_function` entries only.
4. `functions_javascript` generates JavaScript bridges and calls `CustomFunctions.associate` for every worksheet function ID.
5. `manifest_xml` generates the add-in-only XML manifest.
6. `public_url` derives the externally referenced origin or uses `JUPYTEREXCEL_PUBLIC_URL`.

Duplicate worksheet-function IDs are rejected because Office requires every metadata ID to be unique. Ribbon functions do not participate in that worksheet metadata.

### `jupyterexcel/server_extension.py`

Registers Tornado handlers when the Jupyter server extension loads.

`OfficeAddinHandler` regenerates resources from the currently visible notebooks and serves the manifest, metadata, JavaScript, function page, command page, and task pane.

`ExcelModeHandler` receives GET or POST calls under `/Excel/<notebook-path>`. It locates or creates the notebook session, obtains the kernel client, runs notebook cells when initialization is required, invokes the requested function, and serializes the result.

The Python execution helper decodes JSON-encoded argument values before calling the notebook function. This allows Excel values such as numbers, booleans, arrays, and strings to retain their types.

### `jupyterexcel/__init__.py`

Exports `jupyter_function` and `ribbon_function` and declares the Jupyter extension entry points.

## Request lifecycle

For an Excel formula such as `=JUPYTER.ADD(1, 2)`:

1. Excel loads `/manifest.xml`.
2. Excel loads `/public/functions.json` and `/public/functions.js`.
3. `CustomFunctions.associate("ADD", bridge)` connects the metadata ID to its generated bridge.
4. The bridge POSTs `functionName` and numbered arguments to the endpoint for the notebook that owns `ADD`.
5. The server creates or reuses that notebook's session and kernel.
6. The server invokes the Python function and returns valid JSON.
7. The bridge converts the returned rich-display data into an Excel-supported value.

## Public URL and authentication

Manifest URLs must be reachable from the computer running Excel. By default, the origin is derived from the Jupyter server's scheme, host, port, and base path. Set `JUPYTEREXCEL_PUBLIC_URL` when a reverse proxy or separate public address is used.

Office add-ins require HTTPS with a certificate trusted by the Excel computer. Authentication remains controlled by Jupyter. Generated assets must never embed a token or password.

## Current ribbon status

The scanner recognizes `@ribbon_function`, and the task pane displays discovered ribbon entries separately from worksheet functions. The current generator does not create one manifest ribbon control and command handler per decorated ribbon function. Implementing that requires preserving argument-cell mappings, generating stable control/action IDs, registering command actions, reading inputs with `Excel.run`, writing the configured result, and completing the Office command event on every path.

## Caching and invalidation

Excel caches add-in metadata, so newly added or renamed custom functions may require an Excel restart or cache clear. The server caches kernel clients and notebook modification timestamps to avoid rerunning unchanged notebooks. Cache keys must remain based on complete notebook paths.

