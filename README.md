## jupyterexcel Package

### Office.js add-in generation

When the JupyterExcel server extension starts, it scans every notebook visible
to the current Jupyter user. Functions decorated with `jupyter_function` are
published as Excel custom functions; functions decorated with
`ribbon_function` remain separate and are shown in the JupyterExcel task pane. These js files will be referenced by Excel Web Addin manifest.xml.  

```python
from jupyterexcel import jupyter_function, ribbon_function

@jupyter_function(name="ADD", description="Add two numbers",
                  parameter_types={"a": "number", "b": "number"},
                  result_type="number")
def add(a, b=0):
    return a + b
```

## Example
The following screenshot shows the sample notebook file with a function sum. You can download TestingJupyter.ipynb or create your own.  The following is an instance I hosted in google cloud platform, you can open and add a function of yours.<br/>

The following screenshot shows how excel Formula works.
![NotebookExample](https://github.com/luozhijian/jupyterexcel/raw/master/ExcelFormulaScreen.png)

The following screenshot Shows how Ribbon Call Back function works
![Jupyter Ribbon CallBack](https://github.com/luozhijian/jupyterexcel/raw/master/ExcelRibbonScreen.png)


## Explain to Logic behind
Python package jupyterexcel will turn Jyptyer Notebook into Rest API services https://www.jupyterexcel.com/user/jupyterhub/Excel/SUM with json as POST data for parameters. Excel Addin javascript virtual machine will generate JSON format input which pass in from Microsoft custom-functions-runtime.js, make fetch to Jupter Notebook Rest API, wait the result and sync result to Excel cells. Excel Addin Ribbon and Task pane make similiar calls. 

Here are two URLs: https://www.jupyterexcel.com/user/jupyterhub/Excel/SUM  and https://jupyterexcel.com/excel-addin/jupyterhub/functions.js (please open https://jupyterexcel.com/excel-addin/jupyterhub/manifest.xml then view source of https://jupyterexcel.com/excel-addin/jupyterhub/functions.html to see reference to functions.js).  In linux, these two URL looks like from one website. Actually, functions.js from Nginx config, while /Excel/SUM processed by JupyterHub. In windows, Jupyter only support single user JupyterLab. So, there is no need for username jupyterhub part. In the url, /user/jupyterhub will be remove to such as https://www.jupyterexcel.com/Excel/SUM.   Also, there is no tools in windows like Nginx, so in Windows, it will be two sites, such as: https://localhost/excel-addin/functions.js setup in IIS, and https://localhost:8888/Excel for JupyterLab to startup. In order for Excel addin javascript runtime which downloaded functions.js from https://localhost to call https://localhost:8888/Excel, you need setup CORS. 

For your own setup, above www.jupyterexcel.com and username jupyterhub can be replaced. It will be explained below as environment variables.  

## Installation
    For Excel client setup, see the [JupyterExcel add-in setup guide](client-setup.html), including screenshots for token entry, formulas, and ribbon actions.

The following is server setup: 

    setup Jupyter in server, please follow instruction https://jupyter.org/install
    
    pip install jupyterexcel

then run following to check if jupyterexcel is already enabled. 

    jupyter server extension list     
    #if not listed, please use following to enable 
    jupyter server extension enable --py jupyterexcel --sys-prefix

## Server setting

Server setup will be different between Widnows and Linux, partly because, Windows support single user(No need a username), and linux JupyterHub support multiple users.

Please follow config [jupyter server](https://jupyter-notebook.readthedocs.io/en/stable/public_server.html)  or use command
```
    jupyter server --generate-config
	    if the file alraady there, please do not override.  Remember the file path
```


Add Environment variable to bottom of above config file 
```
c.Spawner.environment.update({
    "JUPYTEREXCEL_ASSET_DIR": "/var/www/jupyterexcel/excel-addin",
    "JUPYTEREXCEL_ASSET_URL": "https://www.jupyterexcel.com/excel-addin/",
    "JUPYTEREXCEL_PUBLIC_URL": "https://www.jupyterexcel.com/user/jupyterhub",
    "JUPYTEREXCEL_KEEP_KERNEL_READY": "1",
	"JUPYTEREXCEL_NAMESPACE":"Jupyter",
})

try:
    import logging
    import os
    from jupyterexcel.hub_autostart import configure_autostart

    os.environ["JUPYTEREXCEL_AUTO_START_USERS"] = "jupyterhub"
	#make sure one instance of Jupyter Kernel will startup and running
    configure_autostart(c)
except Exception:
    logging.getLogger("jupyterhub").exception(
        "JupyterExcel auto-start configuration failed; "
        "continuing without automatic user-server startup."
    )

```

You also need change following values.

For Windows computer, Jupyter only support JupyterLab for one user.  You might setup IIS to provide manifest related html, and js file.  It will make js files and Jupyter server in different server or same server but different port, in that case, you need set allow_origin for CORS.
```
c.IdentityProvider.token = 'ABCD'   #now, it has to use token mode. In the url in Excel, if it is not token, it will cause page forward to ask password, the excel will not work
c.ServerApp.allow_origin = 'https://your-addin-host'  #Use the exact origin hosting your add-in when it differs from Jupyter.
c.ServerApp.allow_remote_access = True  #if you like to set to access from other computer
```

For Linux, use Nginx, you can make html files,js files, manifest.xml in same server and port as jupyterhub, so, no need to set CORS.

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

## Environment Variables

All six settings are ordinary process environment variables. **Spawner** and
**OS environment** describe how they reach the process that reads them:

- **JupyterHub:** put the first five settings in `c.Spawner.environment` in
  `jupyterhub_config.py`. JupyterHub passes them to each user's Jupyter server.
  This block does not belong in `jupyter_server_config.py`.
- **Standalone Jupyter:** set the first five in the terminal or service environment
  before launching Jupyter. There is no Spawner in this setup.
- **Hub startup:** set `JUPYTEREXCEL_AUTO_START_USERS` in the Hub process environment,
  or through `os.environ` in `jupyterhub_config.py` before `configure_autostart(c)`.
  Putting it only in `c.Spawner.environment` will not start user servers.

Setting `os.environ` changes only the current Python process and its subsequently
inheriting children; it does not permanently change Windows or Linux settings.
JupyterHub filters inheritance, so a variable set in the Hub's OS environment is
not automatically passed to user servers. Use `c.Spawner.environment` explicitly,
or configure `c.Spawner.env_keep` for selected inherited variables. See the
[JupyterHub Spawner environment reference](https://jupyterhub.readthedocs.io/en/latest/reference/api/spawner.html#jupyterhub.spawner.Spawner.environment).

| Variable | Where to set it | Purpose, default, and example |
| --- | --- | --- |
| `JUPYTEREXCEL_ASSET_DIR` | Spawner on Hub; OS environment for standalone Jupyter | **Required.** Absolute, writable directory for generated manifest, JavaScript, and HTML files. Example: `/var/www/jupyterexcel/excel-addin` or `C:\Websites\JupyterExcel\excel-addin`. On Hub, an encoded username subfolder is appended automatically. |
| `JUPYTEREXCEL_ASSET_URL` | Spawner on Hub; OS environment for standalone Jupyter | **Required.** Public HTTPS URL serving `ASSET_DIR`, without a query or fragment. Example: `https://www.jupyterexcel.com/excel-addin`. On Hub, the username is appended automatically, so do not include it here. Setting this does not configure IIS or Nginx; configure that server separately. |
| `JUPYTEREXCEL_PUBLIC_URL` | Spawner on Hub; OS environment for standalone Jupyter | Jupyter API base URL reachable from Excel. Example: `https://www.jupyterexcel.com/user/alice`. Include the user's server path on Hub. If unset, the extension logs an error and derives a URL from Jupyter's server settings; set it explicitly behind a reverse proxy. This is the API address, not the static asset address. |
| `JUPYTEREXCEL_KEEP_KERNEL_READY` | Spawner on Hub; OS environment for standalone Jupyter | Set `1` to start and maintain the managed kernel before an Excel request. Also accepts `true`, `yes`, or `on`, ignoring case. Unset or `0` disables proactive startup; the first request initializes the kernel instead. It does not start a stopped Hub user server. |
| `JUPYTEREXCEL_NAMESPACE` | Spawner on Hub; OS environment for standalone Jupyter | Formula prefix, such as `MyCompany` for `=MyCompany.My_Join(...)`. Defaults to `Jupyter` when unset or blank. Surrounding whitespace is trimmed. Use 1–32 ASCII characters, starting with a letter, followed by letters, digits, periods, or underscores. |
| `JUPYTEREXCEL_AUTO_START_USERS` | Hub OS/process environment only | Comma-separated existing Hub usernames, such as `alice,bob`. With `configure_autostart(c)`, starts their default user servers when Hub starts. Unset or blank disables this feature. It does not create accounts or start named servers; it has no effect in standalone Jupyter. |

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

Run in PowerShell, then start Jupyter from that same terminal:

```powershell
$env:JUPYTEREXCEL_ASSET_DIR = "C:\Websites\JupyterExcel\excel-addin"
$env:JUPYTEREXCEL_ASSET_URL = "https://localhost/excel-addin"
$env:JUPYTEREXCEL_PUBLIC_URL = "https://localhost:8888"
$env:JUPYTEREXCEL_KEEP_KERNEL_READY = "1"
$env:JUPYTEREXCEL_NAMESPACE = "Jupyter"
jupyter lab
```

Use URLs matching your actual HTTPS and static-server configuration. These
PowerShell assignments apply to the current session and processes started from
it. On Linux, use `export JUPYTEREXCEL_NAMESPACE="Jupyter"` and the same pattern
for the other variables before starting Jupyter. For a service, configure its
service environment instead of relying on an interactive terminal.

Restart the relevant process after changing its environment. On Hub, restart Hub
to apply its configuration, and stop/start existing user servers to receive new
Spawner values. After changing the namespace, reload the updated manifest in
Excel as described below.

## Formula names

Worksheet function names retain their original case, underscores, and periods.
Use `@jupyter_function` or `@jupyter_function()` to export the Python function
name, or `@jupyter_function(name="My_Join")` to provide an explicit Excel name.
For example, `def underscore_join(...)` becomes `Jupyter.underscore_join(...)`.
`string.join` and `string_join` are distinct names; names differing only in case
are rejected as duplicates because Excel names are case-insensitive. Generated
IDs and names preserve spelling; Excel may display capitalization differently.
Unsupported characters are rejected instead of silently renamed.

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
1. Able to support Javascript, in that case, all formula call can be happen in Excel Addin Javascript virtual machine or runtime. No need to call back to server for calculation.
2. Kernel management, now, kernel manage is simple start a named kernel.
3. Latest Python multiple thread support
4. Multiple user release: how to release for multiple users, share a same folder, while keep individual user release?
5. Minimize the javascript code.  
6. Deal with multiple virtual environment
7. Save incoming data for future unit test

## Reference
read some code from [appmode](https://github.com/oschuett/appmode)

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
