## jupyterexcel Package

### Office.js add-in generation

When the JupyterExcel server extension starts, it scans every notebook visible
to the current Jupyter user. Functions decorated with [jupyter_function](https://jupyterexcel.com/excel-addin/jupyter_function.html) are
published as Excel custom functions; functions decorated with
[ribbon_function](https://jupyterexcel.com/excel-addin/ribbon_function.html) remain separate and are shown in the JupyterExcel task pane. The generated JavaScript files are referenced by the Excel web add-in’s `manifest.xml`.

```python
from jupyterexcel import jupyter_function, ribbon_function

@jupyter_function(name="ADD", description="Add two numbers",
                  parameter_types={"a": "number", "b": "number"},
                  result_type="number")
def add(a, b=0):
    return a + b
```

## Example

The example uses a sample notebook containing a `Sum` function. You can download `JupyterFunctions.ipynb` from this folder or create your own notebook.

The following screenshot shows how Excel formulas work.
![NotebookExample](https://github.com/luozhijian/jupyterexcel/raw/master/ExcelFormulaScreen.png)

The following screenshot shows how a ribbon callback function works.
![Jupyter Ribbon CallBack](https://github.com/luozhijian/jupyterexcel/raw/master/ExcelRibbonScreen.png)


## How it works
The `JupyterExcel` Python package exposes Jupyter notebook functions through REST API endpoints, such as https://www.jupyterexcel.com/user/jupyterhub/Excel/SUM, with parameters sent as JSON in the POST body. The Excel add-in’s JavaScript runtime receives the function arguments, sends them to the Jupyter REST API using `fetch`, waits for the result, and sync it back to Excel. Ribbon actions and the task pane make similar calls.

There are two types of URLs: one points to files that Excel downloads when loading the add-in (such as `manifest.xml`), and the other points to API endpoints that process Excel function calls. Examples of these two types of URLs are [https://jupyterexcel.com/**excel-addin**/jupyterhub/manifest.xml](https://jupyterexcel.com/excel-addin/jupyterhub/manifest.xml) and https://www.jupyterexcel.com/user/jupyterhub/Excel/SUM. If you open https://jupyterexcel.com/excel-addin/jupyterhub/functions.json, you can see the description of the `Sum` function shown above. The `functions.json` file is one of the files generated from the notebook above by the JupyterExcel package.

In the Linux setup, these two types of URLs appear to belong to one website, but they are handled by two different services. In the Nginx configuration, **excel-addin** is mapped to the folder `/var/www/jupyterexcel/excel-addin` where JupyterExcel stores the generated Excel add-in files when notebooks are saved. All other requests are forwarded to JupyterHub for processing.

The Windows setup described here uses standalone, single-user JupyterLab, so the URL does not need the `/user/jupyterhub` segment. For example, the endpoint becomes https://www.jupyterexcel.com/Excel/SUM. This setup uses two sites: IIS serves the add-in files, such as https://localhost/functions.js or https://localhost/manifest.xml, and JupyterLab handles API requests at https://localhost:8888/. The URL https://localhost/functions.js does not need the **excel-addin** path segment because IIS serves these files as a separate website. In the Linux Nginx example, the **excel-addin** path distinguishes static-file requests from requests forwarded to JupyterHub. To allow the Excel add-in’s JavaScript runtime, which downloads and runs `functions.js` from https://localhost, to call the Jupyter service at https://localhost:8888/Excel, configure CORS.

For your own setup, replace `www.jupyterexcel.com`, `localhost`, and the username `jupyterhub` as appropriate. These values are configured through the environment variables explained below.

## Prerequisites

JupyterExcel requires **Python 3.9 or later**. Installing the package with pip
also installs these runtime dependencies automatically:

| Package | Required version |
| --- | --- |
| `jupyter-server` | `>=2,<3` |
| `jupyter-client` | `>=8,<9` |
| `ipykernel` | `>=6,<8` |
| `tornado` | `>=6.3` |

For a working deployment, you also need:

- A Python kernel registered as `python3`, which JupyterExcel currently uses.
  Check it with `jupyter kernelspec list`.
- JupyterLab 4 if you want to edit notebooks in JupyterLab and use the bundled
  JupyterExcel toolbar extension. Install it separately with
  `python -m pip install "jupyterlab>=4,<5"`.
- JupyterHub only for a multi-user deployment; it is not required for standalone
  JupyterLab. Install JupyterExcel in each user's server environment.
- Any libraries imported by your notebooks, installed in the environment used
  by the `python3` kernel. Streamlit and pandas are not required by JupyterExcel
  itself.
- Microsoft Excel with support for Office.js custom functions and SharedRuntime
  1.1, and permission to load the add-in manifest.
- An HTTPS static web server, such as IIS or Nginx, to serve the generated add-in
  files, with a certificate trusted by the computer running Excel. Configure
  `JUPYTEREXCEL_ASSET_DIR` and `JUPYTEREXCEL_ASSET_URL` as described below, and
  make the Jupyter API reachable from Excel over HTTPS.

Install JupyterExcel in the Jupyter server environment. If your `python3` kernel
uses a separate virtual environment, install JupyterExcel there too so notebook
imports of its decorators work.

The `build` and `twine` packages are release tools, not runtime dependencies.
Install them in a separate release environment when building or publishing the
package. Node.js is needed to rebuild the frontend, but not to install the
Python package with its prebuilt JupyterLab extension.

## Installation

For Excel client setup, see the [JupyterExcel add-in setup guide](https://www.jupyterexcel.com/excel-addin/client-setup.html).

To set up the server:

Install Jupyter on the server by following the instructions at https://jupyter.org/install. Then install JupyterExcel:

    pip install jupyterexcel

Then run the following command to check whether `jupyterexcel` is already enabled:

    jupyter server extension list
    # If it is not listed as enabled, use the following command to enable it:
    jupyter server extension enable --py jupyterexcel --sys-prefix


## Environment Variables

All six settings are ordinary process environment variables. **Spawner** and
**OS environment** describe how they reach the process that reads them:

- **JupyterHub:** put the first five settings in `c.Spawner.environment` in
  `jupyterhub_config.py`. JupyterHub passes them to each user's Jupyter server.
  The `c.Spawner.environment` block belongs in `jupyterhub_config.py`, because
  it configures how JupyterHub launches user servers. For standalone Jupyter,
  set environment variables before startup or use `os.environ` assignments in
  `jupyter_server_config.py`.
- **Standalone Jupyter:** set the first five in the terminal or service environment
  before launching Jupyter. There is no Spawner in this setup.
  On native Windows, use this **standalone** setup, as JupyterHub is not officially supported there (use a Linux environment, a Linux container, or a Linux VM for JupyterHub).
- **Hub startup:** set `JUPYTEREXCEL_AUTO_START_USERS` in the Hub process environment,
  or through `os.environ` in `jupyterhub_config.py` before `configure_autostart(c)`.
  Putting it only in `c.Spawner.environment` will not start user servers.

Setting `os.environ` changes only the current Python process and any child
processes that subsequently inherit its environment; it does not permanently change Windows or Linux settings.
JupyterHub filters inheritance, so a variable set in the Hub's OS environment is
not automatically passed to user servers. Use `c.Spawner.environment` explicitly,
or configure `c.Spawner.env_keep` for selected inherited variables. See the
[JupyterHub Spawner environment reference](https://jupyterhub.readthedocs.io/en/latest/reference/api/spawner.html#jupyterhub.spawner.Spawner.environment).

| Variable | Where to set it | Purpose, default, and example |
| --- | --- | --- |
| `JUPYTEREXCEL_ASSET_DIR` | Spawner on Hub; OS environment for standalone Jupyter | **Required.** Absolute directory writable by Jupyter for generated manifest, JavaScript, and HTML files. Example: `/var/www/jupyterexcel/excel-addin` or `C:\Websites\JupyterExcel\excel-addin`. On Hub, an encoded username subfolder is appended automatically. |
| `JUPYTEREXCEL_ASSET_URL` | Spawner on Hub; OS environment for standalone Jupyter | **Required.** Public HTTPS URL serving `ASSET_DIR`, without a query or fragment. It is the base URL for `manifest.xml`. Example: `https://www.jupyterexcel.com/excel-addin`. On Hub, the username is appended automatically, so do not include it here. Setting this does not configure IIS or Nginx; configure that server separately. |
| `JUPYTEREXCEL_PUBLIC_URL` | Spawner on Hub; OS environment for standalone Jupyter | Jupyter API base URL reachable from Excel. Example: `https://www.jupyterexcel.com/user/alice` or `https://localhost:8888` for Windows. Include the user's server path on Hub. If unset, the extension logs an error and derives a URL from Jupyter's server settings; set it explicitly behind a reverse proxy. This is the API address, not the static asset address above. |
| `JUPYTEREXCEL_KEEP_KERNEL_READY` | Spawner on Hub; OS environment for standalone Jupyter | Set `1` to start and maintain the managed kernel before an Excel request. Also accepts `true`, `yes`, or `on`, ignoring case. Unset or `0` disables proactive startup; the first request initializes the kernel instead. It does not start a stopped Hub user server. |
| `JUPYTEREXCEL_NAMESPACE` | Spawner on Hub; OS environment for standalone Jupyter | Formula prefix, such as `MyCompany` for `=MyCompany.Sum(...)`. Defaults to `Jupyter` when unset or blank. Surrounding whitespace is trimmed. Use 1–32 ASCII characters, starting with a letter, followed by letters, digits, periods, or underscores. |
| `JUPYTEREXCEL_AUTO_START_USERS` | Hub OS/process environment only | Comma-separated existing Hub usernames, such as `alice,bob`. With `configure_autostart(c)`, starts their default user servers when Hub starts. Unset or blank disables this feature. It does not create accounts or start named servers; it has no effect in standalone Jupyter. |


## Server settings

The examples below use standalone JupyterLab on Windows and multi-user JupyterHub on Linux, so their configuration differs.

Follow the [Jupyter server configuration guide](https://jupyter-notebook.readthedocs.io/en/stable/public_server.html), or generate a server configuration file with:
```
    jupyter server --generate-config
    # If the file already exists, do not overwrite it. Note the file path.
```


For JupyterHub, add the following environment settings to `jupyterhub_config.py` (not `jupyter_server_config.py`). For standalone Jupyter, use the environment-variable example below.
```
c.Spawner.environment.update({
    "JUPYTEREXCEL_ASSET_DIR": "/var/www/jupyterexcel/excel-addin",
    "JUPYTEREXCEL_ASSET_URL": "https://www.jupyterexcel.com/excel-addin/",
    "JUPYTEREXCEL_PUBLIC_URL": "https://www.jupyterexcel.com/user/jupyterhub",
    "JUPYTEREXCEL_KEEP_KERNEL_READY": "1",
    "JUPYTEREXCEL_NAMESPACE": "Jupyter",
})

```

Adjust the following settings for your deployment.

For the standalone Windows setup, you can use IIS to serve the manifest and related HTML and JavaScript files. If the add-in files and Jupyter API use different origins—for example, different ports on the same server—set `allow_origin` for CORS.
```
c.IdentityProvider.token = 'ABCD'   # Use token authentication; a redirect to a password login page will not work for Excel API calls.
c.ServerApp.allow_origin = 'https://your-addin-host'  # Use the exact origin hosting your add-in when it differs from Jupyter.
c.ServerApp.allow_remote_access = True  # Enable access from other computers.
```

The following JupyterHub configuration reduces the initial response time by starting the configured user server and keeping its managed kernel ready for Excel requests. Append it after the Spawner settings in `jupyterhub_config.py`.

```
try:
    import logging
    import os
    from jupyterexcel.hub_autostart import configure_autostart

    os.environ["JUPYTEREXCEL_AUTO_START_USERS"] = "jupyterhub"
    # Start the configured user server and keep its managed Jupyter kernel ready.
    configure_autostart(c)
except Exception:
    logging.getLogger("jupyterhub").exception(
        "JupyterExcel auto-start configuration failed; "
        "continuing without automatic user-server startup."
    )

```

On Linux, Nginx can serve the HTML, JavaScript, and `manifest.xml` files from the same origin as JupyterHub, so cross-origin API access (CORS) is unnecessary. A sample Nginx configuration follows:

```
server {
    server_name jupyterexcel.com www.jupyterexcel.com;

        # Public Excel add-in assets.
    #
    # URL:
    #   /excel-addin/user1/functions.js
    #
    # Filesystem:
    #   /var/www/jupyterexcel/excel-addin/user1/functions.js
    location ^~ /excel-addin/ {
        alias /var/www/jupyterexcel/excel-addin/;

        # Only permit reading static files.
        limit_except GET HEAD OPTIONS {
            deny all;
        }

        # Prevent directory listings.
        autoindex off;

        # Return correct content types.
        default_type application/octet-stream;

        types {
            application/javascript js;
            application/json       json;
            application/xml        xml;
            text/html              html htm;
            text/css               css;
            image/png              png;
            image/svg+xml          svg;
            image/x-icon           ico;
        }

        # Useful when the files are regenerated frequently.
        etag on;
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;

        # Allow Excel's web runtime to request these assets.
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, HEAD, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type" always;

        add_header X-Content-Type-Options "nosniff" always;

        # Do not serve hidden files such as .env or .git.
        location ~ (^|/)\. {
            deny all;
        }
    }

	    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/kernels/ {
            proxy_pass http://localhost:8000/api/kernels/;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
        }


    listen [::]:443 ssl ipv6only=on; # managed by Certbot
    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/jupyterexcel.com/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/jupyterexcel.com/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot
}
```

### Example: JupyterHub

Place this in `jupyterhub_config.py`. The URL example assumes default user servers
under `/user/<username>/`; adjust the public hostname and any proxy prefix.

```python
import os
from urllib.parse import quote
from jupyterexcel.hub_autostart import configure_autostart

c.Spawner.environment.update({
    "JUPYTEREXCEL_ASSET_DIR": "/var/www/jupyterexcel/excel-addin",
    "JUPYTEREXCEL_ASSET_URL": "https://www.jupyterexcel.com/excel-addin",
    "JUPYTEREXCEL_PUBLIC_URL": lambda spawner: (
        "https://www.jupyterexcel.com/user/" + quote(spawner.user.name, safe="")
    ),
    "JUPYTEREXCEL_KEEP_KERNEL_READY": "1",
    "JUPYTEREXCEL_NAMESPACE": "Jupyter",
})

# Read by the Hub, not by the spawned user's server.
os.environ["JUPYTEREXCEL_AUTO_START_USERS"] = "alice,bob"
configure_autostart(c)  # Call once, after other Spawner hooks are configured.
```

The autostart helper enables `KEEP_KERNEL_READY=1` for the listed users unless
already set in their Spawner environment. If absent there, a Hub-process
`KEEP_KERNEL_READY` value overrides that helper default. The explicit `1` in the
example above enables keep-ready for all spawned users, including users not in
`AUTO_START_USERS`.

### Example: standalone Jupyter on Windows


Run in PowerShell, then start Jupyter from that same terminal using port 8888:

```powershell
$env:JUPYTEREXCEL_ASSET_DIR = "C:\Websites\JupyterExcel\excel-addin"
$env:JUPYTEREXCEL_ASSET_URL = "https://localhost"
$env:JUPYTEREXCEL_PUBLIC_URL = "https://localhost:8888"
$env:JUPYTEREXCEL_KEEP_KERNEL_READY = "1"
$env:JUPYTEREXCEL_NAMESPACE = "Jupyter"
jupyter lab --ServerApp.certfile="C:\Users\xxxx\.office-addin-dev-certs\localhost.crt" --ServerApp.keyfile="C:\Users\xxxx\.office-addin-dev-certs\localhost.key" --ServerApp.port=8888 --ServerApp.port_retries=0 --ServerApp.allow_origin="https://localhost"
```

Use URLs matching your actual HTTPS and static-server configuration. These
PowerShell assignments apply to the current session and processes started from
it. On Linux, use `export JUPYTEREXCEL_NAMESPACE="Jupyter"` and the same pattern
for the other variables before starting Jupyter. For a service, configure its
service environment instead of relying on an interactive terminal.

Restart the relevant process after changing its environment.

Once files have been generated in `C:\Websites\JupyterExcel\excel-addin`, you can set up IIS.

![Windows IIS Sample Setup](https://github.com/luozhijian/jupyterexcel/raw/master/WindowsIISSetup.png)

## Formula names

Worksheet function names retain their original case, underscores, and periods.
Use `@jupyter_function` or `@jupyter_function()` to export the Python function
name, or `@jupyter_function(name="My_Join")` to provide an explicit Excel name.
For example, `def underscore_join(...)` becomes `Jupyter.underscore_join(...)`.
`string.join` and `string_join` are distinct names; names differing only in case
are rejected as duplicates because Excel names are case-insensitive. Generated
IDs and names preserve spelling; Excel may display capitalization differently.
Unsupported characters are rejected instead of silently renamed.

Sample jupyter_function: https://jupyterexcel.com/excel-addin/jupyter_function.html
Sample ribbon_function: https://jupyterexcel.com/excel-addin/ribbon_function.html

## Formula namespace

Set `JUPYTEREXCEL_NAMESPACE` before starting Jupyter to choose the formula prefix:

```powershell
$env:JUPYTEREXCEL_NAMESPACE = "MyCompany"
```

The generated manifest then exposes formulas such as `=MyCompany.ADD(1,2)`.
Unset, empty, or whitespace-only values default to `Jupyter`; surrounding
whitespace is trimmed. Supported values are 1-32 ASCII characters, begin with a
letter, and contain only letters, digits, periods, or underscores. Invalid values
stop asset generation with a clear error and leave previously published assets intact.

This applies to all worksheet functions, including built-ins. Function IDs and
API endpoints do not change. For JupyterHub, set it in the user's spawned server
environment. Restart that server after changing its environment and reload the
updated manifest in Excel (clearing its add-in cache if necessary). Existing
workbooks are not migrated automatically to a new formula namespace.

## Documentation

- [Development and testing](Markdowns/DEVELOPMENT.md)
- [Architecture](Markdowns/ARCHITECTURE.md)
- [Notebook actions](Markdowns/NOTEBOOK_ACTIONS.md)
- [Built-in functions](Markdowns/BUILTIN_FUNCTIONS.md)
- [Save and reload](Markdowns/SAVE_AND_RELOAD.md)
- [JupyterHub automatic startup](Markdowns/HUB_AUTO_START.md)

## Future Development Plan

1. Add support for JavaScript functions so calculations can run in the Excel add-in’s JavaScript runtime without calling the server.
2. Improve kernel management, which currently starts a named kernel.
3. Support the latest Python multithreading features.
4. Support multi-user deployments with a shared folder while retaining individual user releases.
5. Minify the JavaScript code.
6. Support multiple virtual environments.
7. Save incoming data for future unit tests.

## Reference

Some implementation ideas were informed by [appmode](https://github.com/oschuett/appmode).

## License

Versions distributed with the current [LICENSE](LICENSE) use **Business Source
License 1.1** (SPDX: BUSL-1.1). BSL is source-available, not an open-source license
before the Change Date. The full LICENSE controls; this is a summary.

| Use | Production-use permission |
| --- | --- |
| Individuals, for personal purposes | Free |
| Nonprofit organizations and nonprofit schools, for internal purposes | Free, regardless of user count |
| Government-operated public schools, for their own students and staff | Free, regardless of user count |
| Government-operated public universities, including hosting for anyone | Free for the university and all users of its hosted service, regardless of affiliation or user count |
| Other government organizations | Separate commercial license required |
| For-profit organizations, including for-profit schools, for internal purposes | Free for up to five distinct production users in any rolling 30-day period |
| Other providers offering JupyterExcel as a hosted service to third parties | Separate commercial license required, regardless of user count or organization type |

- Count people, including employees and contractors, across accounts and
  installations. Six people using one shared login still count as six.
- A for-profit organization has a one-time **60-calendar-day grace period**
  beginning when it first exceeds five production users. Afterward, obtain a
  commercial license or return to the five-user rolling 30-day limit. The grace
  period does not reset with a new installation, version, or later increase.
- The grace period does not permit excluded government or hosted-service use.
- Government-operated public universities may host JupyterExcel for anyone,
  including outside individuals and organizations. Both the university and users
  of that hosted service are exempt from commercial-license and user-count
  requirements. Outside organizations' independently operated deployments
  remain subject to the ordinary terms.
- Other qualifying schools and nonprofit universities may host internally for
  their own students and staff; hosting for outside organizations requires a
  commercial license. Using AWS or another cloud for internal purposes is not
  itself excluded.
- Non-production evaluation, development, and testing remain free under BSL.
- Each version converts to the [MIT License](LICENSE-MIT) four years after its
  first public distribution under BSL. A new version does not reset an earlier
  version's conversion date.

For commercial licensing, contact [support@jupyterexcel.com](mailto:support@jupyterexcel.com).

Previously released MIT versions retain their MIT permissions. LICENSE-MIT also
supplies the future Change License; it does not grant immediate MIT rights to
new BSL-only project changes. Third-party licenses remain unchanged; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
User-created notebooks and data are not automatically relicensed by installing
JupyterExcel. No user tracking or license-enforcement service has been added.

Generated add-in assets include LICENSE.txt, LICENSE-MIT.txt and
THIRD_PARTY_NOTICES.txt beside manifest.xml.
