# Hub automatic startup

Set `hub.auto_start_users` to an array of existing usernames in the Hub's
administrator-controlled JSON configuration. An empty array disables startup.

```python
from jupyterexcel.hub_autostart import configure_autostart
configure_autostart(c, config_file="/etc/jupyterexcel/jupyterexcel-config.json")
```

Call once in `jupyterhub_config.py`. Alternatively omit `config_file` and select
the file with `JUPYTEREXCEL_CONFIG_FILE` or the Hub working directory.
The helper installs a scoped managed service, preserving existing services,
roles and Spawner hooks. The service receives only the selected file path;
JupyterHub supplies its runtime API URL and token. It starts default servers,
never creates accounts or starts named servers, and retries startup failures.
After startup it stays alive without restarting intentionally stopped servers.

Each user server independently loads its notebook-root JSON or its own
`JUPYTEREXCEL_CONFIG_FILE`. The helper does not set per-user settings or a
keep-ready flag. Every user server maintains its configured `execution.min_kernels`.
See [CONFIGURATION.md](CONFIGURATION.md) for all settings and inspection.
