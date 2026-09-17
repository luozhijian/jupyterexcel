---
name: jupyterexcel
description: Build, modify, diagnose, or test JupyterExcel integrations that expose decorated Jupyter notebook functions through a Python Jupyter Server extension and an Excel Office.js add-in. Use for jupyter_function, ribbon_function, generated manifest.xml, functions.js/functions.json, notebook discovery, or Excel-to-kernel execution. Do not use for unrelated Excel automation or ordinary Jupyter notebook editing.
---

# JupyterExcel

Treat JupyterExcel as one system with two cooperating parts:

- The Python Jupyter Server extension discovers notebook functions, manages notebook kernels, executes calls, and returns JSON-compatible results.
- The Excel Office.js add-in registers worksheet custom functions and ribbon commands, then calls the Jupyter server over HTTPS.

Inspect both parts before changing shared behavior. Trace a function from its Python decorator through notebook discovery, generated Office metadata and JavaScript, HTTP transport, kernel execution, and result conversion.

## Function boundaries

Use `@jupyter_function` only for functions exposed as Excel worksheet formulas. Use `@ribbon_function` only for functions invoked by ribbon controls. Never publish ribbon functions in `functions.json` as worksheet custom functions.

Support `@jupyter_function` with and without arguments when the current API permits it. Preserve these metadata fields when present:

- Stable Excel function ID and display name.
- Description.
- Parameter names, types, descriptions, and optional/default status.
- Result type and dimensionality.
- Owning notebook path and Python function name.

Treat the Excel function ID as persistent API identity. Keep it unique and limit it to letters, numbers, and periods. Do not silently rename an established ID.

For `@ribbon_function`, preserve input-cell mappings, return target, label, and owning notebook. Generate real ribbon command bindings when executable buttons are requested; listing ribbon functions in a task pane is not equivalent.

## Notebook discovery

Scan every notebook visible through the active Jupyter `ContentsManager`, including nested directories. This scopes discovery to the current user's Jupyter root.

Prefer static AST inspection of code cells. Do not execute every notebook merely to generate the manifest. Skip non-code cells and tolerate syntax errors in unrelated cells while reporting actionable discovery failures.

Detect duplicate worksheet-function IDs before publishing metadata. Preserve complete notebook-relative paths so notebooks with the same filename in different directories do not share the wrong session or kernel.

Refresh generated assets when notebooks change, or document when Jupyter and Excel must restart. Excel caches custom-function metadata.

## Office add-in generation

Generate the manifest and referenced resources from the same discovered function set. Unless the project specifies other routes, serve:

```text
/manifest.xml
/public/functions.js
/public/functions.json
/public/functions.html
/commands.html
/taskpane.html
```

Every URL in `manifest.xml` must be reachable from the computer running Excel. Derive it from the running Jupyter server or honor an explicit public setting such as `JUPYTEREXCEL_PUBLIC_URL`. Office add-ins require HTTPS with a trusted certificate. Do not assume `localhost` identifies the Jupyter host when Excel runs on another computer.

For worksheet functions:

- Emit valid Office custom-functions JSON metadata.
- Generate one JavaScript bridge for each decorated function.
- Associate every metadata ID with its bridge using `CustomFunctions.associate`.
- Route each bridge to the notebook that owns the Python function.
- Preserve numbers, booleans, strings, arrays, objects, empty strings, and null values during transport.
- Convert successful Jupyter results into Excel-supported scalar or array values.
- Convert HTTP, authentication, kernel, and Python failures into useful Excel errors.

For ribbon functions, keep manifest control IDs and action IDs stable. Ensure every `ExecuteFunction` action is registered by the command JavaScript and completes its Office event on success and failure.

## Jupyter execution

Use the active server's session manager and kernel manager. Do not retain a process-global server object. Key cached kernel clients by the complete notebook path and invalidate them when the session or kernel changes.

Execute notebook initialization cells only when required by the existing architecture. Avoid unnecessary reruns and reinitialize after relevant notebook content changes. Decode request values before invoking Python so argument types are preserved.

Return valid JSON with the correct content type. Never expose Python `repr` output as JSON. Normalize rich-display results, two-dimensional arrays, timestamps, NumPy values, and exceptions deliberately.

Do not weaken Jupyter authentication or origin policy as a shortcut. Keep tokens, credentials, and certificate material out of generated JavaScript, manifests, logs, and source control.

## Repository workflow

Read repository instructions and inspect Git status before editing. Preserve unrelated local changes, particularly in `server_extension.py` and generated Office assets.

Determine whether a manifest or distribution asset is generated before editing it directly. Update the source or generator when one exists. Maintain compatibility with both `jupyter_server` and classic `notebook` imports while the project supports both.

Avoid adding a Node build dependency to the Python server unless the requested design needs it. Runtime generation is appropriate for notebook-derived metadata.

## Verification

Run focused tests for the changed layer and exercise the complete bridge when the environment permits. At minimum verify:

- Decorators register metadata without changing normal Python calls.
- Nested notebooks are discovered and duplicate IDs are rejected.
- `functions.json` is valid and matches generated JavaScript associations.
- `manifest.xml` is well-formed and its URLs match registered routes.
- Generated JavaScript targets the correct encoded notebook path.
- Scalar, optional, string, boolean, array, and error cases survive round trips.
- Generated ribbon controls reference registered command actions.
- Python modules compile and existing tests pass.

Use an Office manifest validator when available. If live Excel/Jupyter testing cannot be performed, distinguish that limitation from the automated checks that passed.
