# Notebook discovery configuration

The server loads one JSON configuration at startup; see
[CONFIGURATION.md](CONFIGURATION.md) for file selection and required settings.
Its `discovery` section selects folders relative to the Jupyter notebook root,
even when the selected configuration file is in a central directory.

```json
"discovery": {
  "include": [
    {"folder": ".", "recursive": false},
    {"folder": "shared", "recursive": true}
  ]
}
```

The default selects only root-level notebooks. Overlapping includes are
deduplicated and notebook execution order is path order. An empty include list
selects no notebooks; JavaScript built-ins remain available. Invalid folder
paths and unavailable included folders fail discovery without falling back.

Asset discovery and managed kernels use the same startup configuration.
Restart Jupyter after changing JSON. Saving notebooks regenerates assets;
Save-and-reload rebuilds the worker notebook snapshot using the existing
configuration. This filter is not an execution permission boundary.

Low-level discovery utilities without a loaded server retain their optional
project-file behavior for standalone tooling. The server always requires a
validated full configuration. `jupyterexcel.json`, used to enable the Jupyter
server extension, is a separate file.
