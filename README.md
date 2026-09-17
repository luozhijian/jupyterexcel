## jupyterexcel Package

### Office.js add-in generation

When the JupyterExcel server extension starts, it scans every notebook visible
to the current Jupyter user. Functions decorated with `jupyter_function` are
published as Excel custom functions; functions decorated with
`ribbon_function` remain separate and are shown in the JupyterExcel task pane.

```python
from jupyterexcel import jupyter_function, ribbon_function

@jupyter_function(name="ADD", description="Add two numbers",
                  parameter_types={"a": "number", "b": "number"},
                  result_type="number")
def add(a, b=0):
    return a + b
```

The generated manifest is served at
`https://<jupyter-host>:<port>/manifest.xml` (with a compatibility alias at
`/jupyterexcel/manifest.xml`). Its JavaScript,
metadata, and HTML URLs point back to the same Jupyter server. To publish a
different externally reachable URL, set this before starting Jupyter:

Environment variables:
 

Use HTTPS with a certificate trusted by the computer running Excel. Restart
Excel (or clear its add-in cache) after decorated functions change because
Excel caches custom-function metadata.

This is a python package to make Jupyter.ipynb file a web api with json result. You can call Jupyter from Excel Formula or Ribbon CallBack Functions
SourceCode in  [JupyterExcel](https://github.com/luozhijian/jupyterexcel)

Before install, please download  https://jupyterexcel.com/excel-addin/jupyterhub/manifest.xml to try its formula function and excel ribbon.  If you think it works, you can modify the url in the sheet to your jupyter page and save it as "Addin" file.

## Example
The following screenshot shows the sample notebook file with a function sum. You can download TestingJupyter.ipynb or create your own.  The following is an instance I hosted in google cloud platform, you can open and add a function of yours.<br/>

The following screenshot shows how excel Formula works. 
![NotebookExample](https://github.com/luozhijian/jupyterexcel/raw/master/ExcelFormulaScreen.png)

The following screenshot Shows how Ribbon Call Back function works
![Jupyter Ribbon CallBack](https://github.com/luozhijian/jupyterexcel/raw/master/ExcelRibbonScreen.png)
 

## Installation 

    pip install jupyterexcel

then run 

    jupyter serverextension enable --py jupyterexcel

## Server setting

Server setup will be different between Widnows and Linux, partly because, Windows support single user(No need a username), and linux JupyterHub support multiple users. 

Environment variable: 
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
Please follow config [jupyter server](https://jupyter-notebook.readthedocs.io/en/stable/public_server.html)  or use command 
```
    jupyter notebook --generate-config 
	    if the file alraady there, please do not override.  Remember the file path
```

You also need change following values. 

For Windows computer, Jupyter only support JupyterLab for one user.  You might setup IIS to provide manifest related html, and js file.  It will make js files and Jupyter server in different server or same server but different port, in that case, you need set allow_origin for CORS.  
```
c.NotebookApp.token = 'ABCD'   #now, it has to use token mode. In the url in Excel, if it is not token, it will cause page forward to ask password, the excel will not work
c.NotebookApp.allow_origin = '*'  #allow any origin to access your server.  You can ignore following 3 connections,if you connect only from local computer
c.NotebookApp.allow_remote_access = True  #if you like to set to access from other computer
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


## Future Development Plan
1. Able to support Javascript, in that case, all formula call can be happen in Excel Addin Javascript virtual machine or runtime. No need to call back to server for calculation.  
2. Kernel management, now, kernel manage is simple start a named kernel. 
3. Latest Python multiple thread support

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
