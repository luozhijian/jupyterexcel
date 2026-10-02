"""Opt-in JupyterHub-managed startup of existing users' default servers."""
import asyncio
import json
import logging
import os
import sys
from urllib.parse import quote

from tornado.httpclient import AsyncHTTPClient, HTTPClientError

NAME = 'jupyterexcel-autostart'
from .config import CONFIG_ENV, load_config, validate_users


def parse_users(value):
    return validate_users(value)


def configure_autostart(config, config_file=None):
    """Call last in jupyterhub_config.py; select an administrator-owned JSON file."""
    snapshot = load_config(path=config_file)
    users = snapshot['config']['hub']['auto_start_users']
    if not users:
        return
    services = list(config.JupyterHub.get('services', []))
    roles = list(config.JupyterHub.get('load_roles', []))
    if any(item.get('name') == NAME for item in services + roles):
        raise ValueError('JupyterExcel autostart is already configured')
    services.append({'name': NAME,
                     'command': [sys.executable, '-m', 'jupyterexcel.hub_autostart'],
                     'environment': {CONFIG_ENV: snapshot['path']}})
    roles.append({'name': NAME, 'services': [NAME],
                  'scopes': [scope + '!user=' + user for user in users
                             for scope in ('read:servers', 'servers')]})
    config.JupyterHub.services = services
    config.JupyterHub.load_roles = roles


async def ensure_server(request, username):
    """Return True only when ready; no account creation or named-server changes."""
    path = 'users/' + quote(username, safe='')
    model = await request(path)
    server = model.get('servers', {}).get('', {})
    if server.get('ready'):
        return True
    if not server.get('pending'):
        await request(path + '/server', method='POST')
    return False


async def run(users, request, log, sleep=asyncio.sleep):
    remaining = set(users)
    while remaining:
        for username in sorted(remaining):
            try:
                if await ensure_server(request, username):
                    remaining.remove(username)
                    log.info('JupyterExcel user server ready: %s', username)
            except HTTPClientError as error:
                # Do not log response bodies, API URLs or credentials.
                log.warning('JupyterExcel startup for %s failed (HTTP %s); retrying', username, error.code)
            except Exception as error:
                log.warning('JupyterExcel startup for %s failed (%s); retrying', username, type(error).__name__)
        if remaining:
            await sleep(30)
    # Managed services must stay alive. Do not respawn deliberately stopped servers.
    await asyncio.Event().wait()


async def main():
    users = load_config()['config']['hub']['auto_start_users']
    if not users:
        raise ValueError('hub.auto_start_users is empty')
    api = os.environ['JUPYTERHUB_API_URL'].rstrip('/')
    token = os.environ['JUPYTERHUB_API_TOKEN']
    client = AsyncHTTPClient()

    async def request(path, method='GET'):
        response = await client.fetch(api + '/' + path, method=method,
                                      headers={'Authorization': 'token ' + token},
                                      body=b'' if method == 'POST' else None,
                                      request_timeout=60, follow_redirects=False)
        return json.loads(response.body) if response.body else {}
    try:
        await run(users, request, logging.getLogger(NAME))
    finally:
        client.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
