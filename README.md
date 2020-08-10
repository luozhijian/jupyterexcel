## jupyterexcel Package

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


![NotebookExample](https://github.com/luozhijian/jupyterexcel/blob/master/NotebookExample.png)

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
