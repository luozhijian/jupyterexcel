# -*- coding: utf-8 -*-
"""
Created on Wed May 29 22:22:45 2019

@author: Jim Luo
"""

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="jupyterexcel",
    version="0.0.11",
    author="Jim Luo",
    author_email="luozhijian@gmail.com",
    description="A python Jupyter extensions to make notebooks web api for Excel to call using UDF forumla or Ribbon Callback. Jupyter Excel, Python Excel",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/luozhijian/jupyterexcel",
    packages=setuptools.find_packages(),
    package_data={"jupyterexcel": ["addin_template/*", "addin_template/assets/*"]},
    data_files=[("etc/jupyter/jupyter_server_config.d", ["jupyterexcel.json"])],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
