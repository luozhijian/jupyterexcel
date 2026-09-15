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

```powershell
$env:JUPYTEREXCEL_PUBLIC_URL = "https://localhost:3000"
```

Use HTTPS with a certificate trusted by the computer running Excel. Restart
Excel (or clear its add-in cache) after decorated functions change because
Excel caches custom-function metadata.

This is a python package to make Jupyter.ipynb file a web api with json result. You can call Jupyter from Excel Formula or Ribbon CallBack Functions
SourceCode in  [JupyterExcel](https://github.com/luozhijian/jupyterexcel)

Before install, please download [JupyterExcelTesting.xlsm](https://github.com/luozhijian/jupyterexcel/blob/master/JupyterExcelTesting.xlsm) to try its formula function and excel ribbon.  If you think it works, you can modify the url in the sheet to your jupyter page and save it as "Addin" file.

This Jupyter Excel web api can be connected with Excel addin which call this web api. Excel formula will generate a web api url and through winhttp to get json result. It now works Mac Excel by using [VBA-Web](https://github.com/VBA-tools/VBA-Web).

## Installation 

    pip install jupyterexcel

then run 

    jupyter serverextension enable --py jupyterexcel

## Server setting

Please follow config [jupyter server](https://jupyter-notebook.readthedocs.io/en/stable/public_server.html)  or use command 
```
    jupyter notebook --generate-config 
	    if the file alraady there, please do not override.  Remember the file path
```

and change following values:
```
c.NotebookApp.token = 'ABCD'   #now, it has to use token mode. In the url in Excel, if it is not token, it will cause page forward to ask password, the excel will not work
c.NotebookApp.allow_origin = '*'  #allow any origin to access your server.  You can ignore following 3 connections,if you connect only from local computer
c.NotebookApp.allow_remote_access = True  #if you like to set to access from other computer
c.NotebookApp.ip = '0.0.0.0'   #allow all ip address to connect to this instance 
c.NotebookApp.iopub_data_rate_limit = 32000000  #it might be good to change to a high number, if you will pass out large amount of data. (bytes/sec) Maximum rate at which stream output can be sent on iopub before
```
## Example
The following screenshot shows the sample notebook file with a function sum. You can download TestingJupyter.ipynb or create your own.  The following is an instance I hosted in google cloud platform, you can open and add a function of yours.<br/>
http://www.jupyterexcel.com:8888/Excel/TestingJupyter.ipynb?token=ABCD&functionname=sum&1=11&2=8&3=6 <br/>
http://www.jupyterexcel.com:8888/notebooks/TestingJupyter.ipynb?token=ABCD   please change 34.67.24.96 to your computer name or localhost


![NotebookExample](https://github.com/luozhijian/jupyterexcel/raw/master/NotebookExample.png)

The following screenshot shows how excel Formula works. 
![Jupyter Excel](https://github.com/luozhijian/jupyterexcel/raw/master/ExcelFormulaScreenFull.png)

The following screenshot Shows how Ribbon Call Back function works
![Jupyter Ribbon CallBack](https://github.com/luozhijian/jupyterexcel/raw/master/ExcelRibbonScreen.png)
 

## Future Development Plan
1. Make Excel client side more easier to use, such as generate Excel formula proxy
2. Able to support R, Julia ....
3. It might only support one notebook page

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
