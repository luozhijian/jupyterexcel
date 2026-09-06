# -*- coding: utf-8 -*-

name = "jupyterexcel"

__version__ = '0.1.0'

from .utils import jupyter_function, ribbon_function

__all__ = ["jupyter_function", "ribbon_function"]


# Jupyter Extension points
def _jupyter_nbextension_paths():
    return [dict(
        section="notebook",
        src="",
        dest="jupyterexcel")]

def _jupyter_server_extension_points():
    return [{"module": "jupyterexcel.server_extension"}]


def _jupyter_server_extension_paths():
    return _jupyter_server_extension_points()
