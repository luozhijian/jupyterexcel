"""Opt-in JupyterHub-managed startup of existing users' default servers."""
import asyncio
import inspect
import json
import logging
import os
import sys
from urllib.parse import quote

from tornado.httpclient import AsyncHTTPClient, HTTPClientError

NAME = 'jupyterexcel-autostart'
KEEP = 'JUPYTEREXCEL_KEEP_KERNEL_READY'
USERS = 'JUPYTEREXCEL_AUTO_START_USERS'


def parse_users(value):
    users = list(dict.fromkeys(item.strip() for item in value.split(',') if item.strip()))
    if any(any(c.isspace() or c in ':!/\\?#&=' for c in user) for user in users):
        raise ValueError(USERS + ' must contain comma-separated usernames, not kernel counts')
    return users


def configure_autostart(config, environ=None):
    """Call last in jupyterhub_config.py; requires JupyterHub 2+ scoped services."""

    
    environ = os.environ if environ is None else environ
    users = parse_users(environ.get(USERS, ''))
    logging.getLogger("jupyterhub").info('JupyterForExcel startup for %s', ','.join(users))

    if not users:
        return
    services = list(config.JupyterHub.get('services', []))
    roles = list(config.JupyterHub.get('load_roles', []))
    if any(item.get('name') == NAME for item in services + roles):
        raise ValueError('JupyterExcel autostart is already configured')
    previous = config.Spawner.get('pre_spawn_hook', None)
    explicit = environ.get(KEEP)

    async def prepare(spawner):
        if previous:
            result = previous(spawner)
            if inspect.isawaitable(result):
                await result
        if spawner.user.name in users and not spawner.name:
            # Copy per instance: do not change other users' environment dictionaries.
            env = dict(spawner.environment)
            if KEEP not in env:
                env[KEEP] = explicit if explicit is not None else '1'
            spawner.environment = env

    services.append({'name': NAME,
                     'command': [sys.executable, '-m', 'jupyterexcel.hub_autostart'],
                     'environment': {USERS: ','.join(users)}})
    roles.append({'name': NAME, 'services': [NAME],
                  'scopes': [scope + '!user=' + user for user in users
                             for scope in ('read:servers', 'servers')]})
    config.JupyterHub.services = services
    config.JupyterHub.load_roles = roles
    config.Spawner.pre_spawn_hook = prepare


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
    users = parse_users(os.environ.get(USERS, ''))
    if not users:
        raise ValueError(USERS + ' is empty')
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
