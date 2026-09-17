# Save and reload JupyterExcel

JupyterLab 4 includes a notebook toolbar button, **Save & reload Excel**, and
a command-palette entry, **Save and reload JupyterExcel**.

Install the Python package in the environment running JupyterLab and the user's
Jupyter Server, restart that server, and refresh the browser. On JupyterHub,
restart the user's notebook server. No Node.js installation or JupyterLab rebuild
is required for users: the Python wheel includes the prebuilt frontend.

The command saves the active notebook, waits for asset generation, then reruns
its code cells in the shared JupyterExcel kernel. Unchanged generated assets do
not prevent a reload. Ordinary Save, Ctrl+S, and autosave keep their existing
behavior; they do not trigger this explicit reload.

Reloads serialize with Excel requests and wait for a busy kernel, up to the
configured kernel timeout. They do not interrupt running work. A cold kernel
first initializes exported notebooks, including the selected notebook once.
An initialized kernel reruns only the selected notebook. Full relative paths
are preserved, including notebooks in nested folders.

Code cells can have side effects. If a later cell fails, earlier changes remain.
Reloading does not clear deleted definitions or refresh references imported by
other notebooks. This command also does not refresh Excel's formula metadata.

The frontend uses Jupyter's authenticated request helper, including XSRF headers,
to POST `{"path":"nested/notebook.ipynb"}` to
`<base_url>/jupyterexcel/api/reload`. The endpoint checks contents-read and
kernel-execute authorization and, on Hub, the authenticated server owner.
It publishes assets before requesting execution and reports failures in a
JupyterLab notification. Existing Excel authentication is unchanged.

## Developing and releasing

Activate the Python environment containing JupyterLab 4, with its executables on
PATH. From the repository root:

```sh
cd frontend
npm ci --ignore-scripts
npm test
npm run build
cd ..
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps -w dist
```

Commit frontend sources, package-lock.json, and the generated
`jupyterexcel/labextension` bundle together. Rebuild after frontend changes.
Keep `labextension/install.json` alongside the generated package.json.
Webpack is pinned because newer releases are incompatible with the current
JupyterLab builder's license extraction plugin.

To verify installation, run `jupyter labextension list` and look for
`@jupyterexcel/labextension` enabled and OK. The frontend targets JupyterLab 4;
it is not a classic Notebook nbextension.
