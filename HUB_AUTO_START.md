# Start JupyterExcel user servers with JupyterHub

Install JupyterExcel in both the Hub Python environment and the single-user
server environment. This integration uses JupyterHub 2+ managed services and
scoped REST API permissions. Standalone JupyterLab is unchanged.

At the **end** of your existing `jupyterhub_config.py`, add:

```python
import os
from jupyterexcel.hub_autostart import configure_autostart

os.environ.setdefault('JUPYTEREXCEL_AUTO_START_USERS', 'jupyterhub')
configure_autostart(c)
```

Alternatively set `JUPYTEREXCEL_AUTO_START_USERS=jupyterhub` in the Hub service
environment, then call `configure_autostart(c)` in its configuration. Multiple
users use commas, for example `jupyterhub,jimluo`. Empty/unset disables startup.
The helper must run after existing services, roles and pre-spawn hook settings;
it preserves them. Do not call it twice.

Restart JupyterHub. The managed service waits for the Hub API and starts each
listed user's default server through the configured spawner. Users must already
exist in Hub and meet the authenticator/spawner requirements. No accounts are
created, passwords supplied, or named servers started. Spawners needing fresh
interactive authentication may still require login.

Running servers are skipped; pending starts are polled every 30 seconds. Failed
starts are retried independently. Hub logs report each ready server or failure.
After all servers are ready, the service remains idle; it does not undo manual
stops or idle-culler shutdowns. Configure the Hub's idle culler separately if
these servers should remain continuously available.

For selected default servers, the pre-spawn hook supplies
`JUPYTEREXCEL_KEEP_KERNEL_READY=1` unless explicitly overridden in the spawner's
environment or the Hub process environment. Explicit `0` remains disabled.
Other users and named servers are unchanged. Existing running servers need a
restart to receive changed environment settings. Kernel readiness begins after
server startup; Excel may need recalculation while notebooks initialize.

Permissions are restricted to reading and starting/stopping the listed users'
servers; no admin role or account-creation permission is granted. The service
uses the API token supplied by Hub and never passes it to user servers.
Keep-ready still works independently for standalone JupyterLab.

Reference: https://jupyterhub.readthedocs.io/en/stable/reference/services.html
