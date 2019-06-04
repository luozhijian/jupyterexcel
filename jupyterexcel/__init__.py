# -*- coding: utf-8 -*-

name = "jupyterexcel"

__version__ = '0.0.2'

# Jupyter Extension points
def _jupyter_nbextension_paths():
    return [dict(
        section="notebook",
        src="",
        dest="jupyterexcel")]

def _jupyter_server_extension_paths():
    return [{"module":"jupyterexcel.server_extension"}]

#EOF
