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
    version="0.0.10",
    author="Jim Luo",
    author_email="luozhijian@gmail.com",
    description="A python Jupyter extensions to make notebooks web api for Excel to call using UDF forumla or Ribbon Callback. Jupyter Excel, Python Excel",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/luozhijian/jupyterexcel",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)


print("\nPlease run the following commands to enable jupyterexcel:")
print("  jupyter serverextension enable --py --sys-prefix jupyterexcel")
print("  also follow up the steps to config server and use token to link to jupyter pages")

#EOF
