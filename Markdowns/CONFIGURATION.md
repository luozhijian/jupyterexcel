# JupyterExcel configuration

All deployment settings are read from one JSON file at server startup. The
complete repository example is `../jupyterexcel-config.json`.

## Selection and lifetime

1. `JUPYTEREXCEL_CONFIG_FILE`, if set, must be an absolute path to a JSON file.
2. Otherwise use `jupyterexcel-config.json` in the ContentsManager notebook root.
3. Missing, malformed or invalid configuration stops extension initialization.

No files are merged. Old per-setting environment variables are not read.
Custom ContentsManagers without a filesystem root must use the explicit path.
UTF-8 and UTF-8 with BOM are supported. Duplicate keys, unknown settings,
unsupported schema versions and invalid types are rejected with the file path.

Settings are frozen at startup. Saving notebooks regenerates assets and reload
still discovers notebook contents, but neither applies changed JSON settings.
Restart the server to apply configuration changes. Relative asset paths resolve
against the selected file's directory; discovery paths always resolve through
the active ContentsManager, relative to the notebook root.

## Settings

`schema_version` defaults to 1. `server.public_url`, `assets.directory` and
`assets.url` are required. Both URLs must be absolute HTTPS URLs without
credentials, query or fragment. The directory must be writable by Jupyter.
Neither URL configures IIS/Nginx, TLS, authentication or CORS for you.

`addin.namespace` defaults to `Jupyter`; it is 1-32 ASCII characters, starts
with a letter and then permits letters, digits, periods and underscores.

`discovery.include` defaults to the root folder (`.`), nonrecursive. Each entry
has a notebook-root-relative `folder` and optional boolean `recursive` (false).
Empty includes intentionally selects no notebooks. Parent traversal is rejected.

`execution` defaults:

| Setting | Default | Meaning |
| --- | --- | --- |
| min_kernels | 1 | Minimum running service kernels, initialized on startup |
| max_kernels | 4 | Maximum service kernels |
| timeout_seconds | 30 | Function response timeout |
| startup_timeout_seconds | 60 | Worker startup/initialization timeout |
| queue_timeout_seconds | 30 | Maximum wait in the request queue |
| max_queue_size | 1000 | Maximum queued requests |
| scale_up_utilization | 0.8 | Busy utilization threshold |
| utilization_window_seconds | 5 | Utilization measurement window |
| queue_scale_up_after_seconds | 1 | Queue delay triggering scale-up |
| scale_up_cooldown_seconds | 1 | Minimum interval between scale-up attempts |

All numeric settings must be positive and finite. Kernel counts and queue
size must be integers; minimum cannot exceed maximum; utilization cannot exceed 1.
There is no keep-ready flag. Managed service kernels are protected from idle
culling and replaced after failure. A minimum running kernel is not a guarantee
of an extra idle kernel during demand. Readiness requires successful notebook
initialization; failures appear in pool status and server logs.

`hub.auto_start_users` defaults to an empty array. Set it to existing usernames
in the Hub administrator's selected configuration and call
`configure_autostart(c, config_file="/absolute/path/jupyterexcel-config.json")`.
Without that argument, the helper uses the path variable or Hub working folder.
User servers independently select their own configuration. Hub identity and
API credentials continue to be provided by JupyterHub, never by this JSON.

## Inspection

```python
import jupyterexcel
jupyterexcel.show_config()
# Preview a central file or specify the notebook root explicitly:
jupyterexcel.show_config(path="C:/JupyterExcel/jupyterexcel-config.json")
jupyterexcel.show_config(root="C:/Notebooks")
```

The function prints the absolute selected path, selection source and complete
effective JSON (including defaults and resolved paths), and returns a copy.
In an ordinary Python/notebook process it explicitly labels the result as a
file preview, not verified running-server state. Its fallback there is the
current working directory; use `root` when that differs from the notebook root.

Within a managed service kernel it reports the exact startup snapshot. Server
code can use `show_config(server_app=app)` for the same result. The existing
authenticated `jupyterexcel/api/status` endpoint also returns `configuration`,
including the startup snapshot and `restart_required` when the file changed or
became unavailable. Configuration is never copied into public Office assets.
