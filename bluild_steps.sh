#!/usr/bin/env bash
# Release steps for JupyterExcel.
# JupyterHub runs using root.

set -euo pipefail

cd /opt/jupyterexcel

# Mark the start time so the install step uses the wheel produced by this run.
build_marker="$(mktemp)"
trap 'rm -f "$build_marker"' EXIT

sudo /opt/jupyterhub/bin/python3 -m build --wheel --no-isolation

wheel_path="$(find /opt/jupyterexcel/dist -maxdepth 1 -type f -name 'jupyterexcel-*.whl' -newer "$build_marker" -print -quit)"
if [[ -z "$wheel_path" ]]; then
    echo "No wheel was produced in /opt/jupyterexcel/dist." >&2
    exit 1
fi

echo "Installing wheel: $wheel_path"

sudo systemctl stop jupyterhub

sudo /opt/jupyterhub/bin/python3 -m pip uninstall -y jupyterexcel

# Install the wheel generated above, without fetching dependencies.
sudo /opt/jupyterhub/bin/python3 -m pip install \
    --no-cache-dir \
    --no-deps \
    "$wheel_path"

/opt/jupyterhub/bin/python3 -m jupyter server extension list

sudo /opt/jupyterhub/bin/python3 -m jupyter \
    server extension enable \
    --py jupyterexcel \
    --sys-prefix

sudo systemctl daemon-reload
sudo systemctl restart jupyterhub

sudo journalctl --vacuum-time=1s
sudo journalctl -u jupyterhub -f
