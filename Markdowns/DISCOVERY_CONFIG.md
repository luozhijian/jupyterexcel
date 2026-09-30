# Project discovery settings

Place `jupyterexcel-config.json` in the Jupyter server's ContentsManager root
(the top of the JupyterLab file browser, not necessarily the package directory).
The repository includes a configuration selecting only root-level notebooks:

```json
{
  "discovery": {
    "include": [
      {"folder": ".", "recursive": false}
    ]
  }
}
```

Add `{"folder": "ExcelFunctions", "recursive": false}` to include notebooks
directly in that folder. Set recursive to true to include its entire subtree.
Paths use `/` and are relative to the server root. Absolute paths, `..`, and
wildcards are rejected. Recursive defaults to false for each explicit entry.
Overlapping entries are deduplicated; notebook execution order is path order.
An empty include list selects no notebooks (JavaScript built-ins remain).

If the file, discovery section, or include setting is absent, the previous
recursive discovery behavior remains. Invalid JSON/settings and unavailable
included folders fail discovery instead of falling back to scanning everything.
Other top-level sections are allowed for future settings; unknown discovery
keys are rejected to catch typos.

Asset discovery and managed-kernel initialization share this selection. Saving
through Jupyter triggers the existing asset-generation hook. For externally
edited configuration, restart JupyterLab/server to regenerate assets. Restart
the managed kernel after changing selection: already executed definitions are
not removed from a running kernel. The pooled executor requires a notebook to be included before Save-and-reload;
that action rebuilds all managed workers from the new selected snapshot.
This is an automatic discovery filter, not an execution permission boundary.

Your existing `jupyterexcel.json` server-extension enablement file is separate.
