# Repository Instructions

These instructions apply to the entire JupyterExcel repository.

## Project model

JupyterExcel consists of a Python Jupyter Server extension and an Excel client. The current Python package dynamically generates Office.js custom-function resources from decorated functions found in notebooks.

Read `ARCHITECTURE.md` before changing cross-layer behavior. Read `DEVELOPMENT.md` for setup, test, and debugging commands. `SKILL.md` contains broader reusable JupyterExcel guidance.

## Before editing

- Inspect `git status --short`; preserve unrelated user changes and untracked files.
- Search before adding a new implementation. Generated Office assets originate in `jupyterexcel/office_addin.py` and are served by `jupyterexcel/server_extension.py`.
- Do not edit a generated manifest or generated JavaScript as though it were source.
- Keep notebook-relative paths complete. Do not reduce nested paths to a basename when selecting sessions, kernels, or endpoints.

## Behavioral boundaries

- `@jupyter_function` defines an Excel worksheet custom function.
- `@ribbon_function` defines ribbon-oriented behavior and must not appear in worksheet-function metadata.
- At present, ribbon functions are discovered and displayed in the task pane; individual executable ribbon controls are not yet generated. Do not claim otherwise unless that behavior is implemented and tested.
- Excel function IDs are stable API identifiers. Keep them unique and composed only of ASCII letters, numbers, periods, and underscores. Preserve supplied case and punctuation; compare names case-insensitively when checking duplicates.
- Notebook discovery must use the Jupyter `ContentsManager` and include nested directories.
- Prefer static AST discovery. Do not execute all notebooks merely to build Office metadata.

## Server and transport invariants

- Use the active Jupyter session manager and kernel manager; do not add process-global server state.
- Cache clients by complete notebook path and handle changed or dead sessions.
- Preserve argument types across JavaScript, HTTP, and Python.
- Return valid JSON, never Python `repr` masquerading as JSON.
- Keep credentials, tokens, and certificates out of generated resources and logs.
- Do not weaken authentication, CORS, or HTTPS configuration to make a test pass.
- Keep compatibility imports for both `jupyter_server` and classic `notebook` unless support is intentionally dropped.

## Generated Office resources

The server currently exposes these primary routes, plus `/jupyterexcel/...` compatibility aliases for Office resources:

```text
/Excel/<notebook-path>
/manifest.xml
/public/functions.js
/public/functions.json
/public/functions.html
/commands.html
/taskpane.html
```

When changing one layer, verify the manifest URLs, registered Tornado routes, JSON IDs, JavaScript associations, and owning notebook endpoints remain consistent.

## Verification

From the repository root, run:

```powershell
python -m unittest discover -s tests -v
python -m py_compile jupyterexcel\utils.py jupyterexcel\office_addin.py jupyterexcel\server_extension.py
git diff --check
```

Use the available Python executable if `python` is not on `PATH`. For manifest changes, also parse the XML and use an Office manifest validator when available. State separately whether live Excel-to-Jupyter testing was performed.


## Protected directory

Do not create, edit, rename, move, or delete anything under:

`.\DoNotChange`

Reading files in this directory is allowed only when necessary. If a requested change requires modifying this directory, stop and ask the user for explicit permission.
