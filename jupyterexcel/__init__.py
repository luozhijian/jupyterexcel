# -*- coding: utf-8 -*-

name = "jupyterexcel"

__version__ = '0.1.0'

from .utils import jupyter_function, ribbon_function

__all__ = ["jupyter_function", "ribbon_function"]


# Jupyter Server validates and loads the package named by the extension point.
# Keep that public entry point at the package root while importing the server
# implementation lazily, so importing decorators does not require Jupyter's
# server dependencies to have been imported first.
def load_jupyter_server_extension(server_app):
    from .server_extension import load_jupyter_server_extension as load

    return load(server_app)


_load_jupyter_server_extension = load_jupyter_server_extension


# Jupyter Extension points
def _jupyter_nbextension_paths():
    return [dict(
        section="notebook",
        src="",
        dest="jupyterexcel")]

def _jupyter_server_extension_points():
    return [{"module": "jupyterexcel"}]


def _jupyter_server_extension_paths():
    return _jupyter_server_extension_points()
