import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from traitlets.config import Config
from jupyterexcel.hub_autostart import configure_autostart, ensure_server, parse_users, run


class AutostartTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_and_environment_precedence(self):
        config = Config()
        previous = AsyncMock()
        config.Spawner.pre_spawn_hook = previous
        config.JupyterHub.services = [{'name': 'existing'}]
        configure_autostart(config, {'JUPYTEREXCEL_AUTO_START_USERS': 'alice,bob'})
        self.assertEqual(len(config.JupyterHub.services), 2)
        self.assertEqual(config.JupyterHub.load_roles[0]['scopes'],
                         ['read:servers!user=alice', 'servers!user=alice',
                          'read:servers!user=bob', 'servers!user=bob'])
        for user, name, initial, expected in [
            ('alice', '', {}, {'JUPYTEREXCEL_KEEP_KERNEL_READY': '1'}),
            ('bob', '', {'JUPYTEREXCEL_KEEP_KERNEL_READY': '0'}, {'JUPYTEREXCEL_KEEP_KERNEL_READY': '0'}),
            ('other', '', {}, {}), ('alice', 'named', {}, {})]:
            spawner = SimpleNamespace(user=SimpleNamespace(name=user), name=name, environment=initial)
            await config.Spawner.pre_spawn_hook(spawner)
            self.assertEqual(spawner.environment, expected)
        self.assertEqual(previous.await_count, 4)

    async def test_hub_explicit_override(self):
        config = Config()
        configure_autostart(config, {'JUPYTEREXCEL_AUTO_START_USERS': 'alice',
                                    'JUPYTEREXCEL_KEEP_KERNEL_READY': '0'})
        spawner = SimpleNamespace(user=SimpleNamespace(name='alice'), name='', environment={})
        await config.Spawner.pre_spawn_hook(spawner)
        self.assertEqual(spawner.environment['JUPYTEREXCEL_KEEP_KERNEL_READY'], '0')

    async def test_ready_pending_and_stopped(self):
        for state, count, ready in [({'ready': True}, 1, True),
                                    ({'pending': 'spawn'}, 1, False), ({}, 2, False)]:
            request = AsyncMock(return_value={'servers': {'': state}})
            self.assertEqual(await ensure_server(request, 'alice'), ready)
            self.assertEqual(request.await_count, count)
            if count == 2:
                request.assert_awaited_with('users/alice/server', method='POST')

    def test_disabled_and_validation(self):
        config = Config()
        configure_autostart(config, {})
        self.assertEqual(dict(config), {})
        self.assertEqual(parse_users('alice, bob,alice'), ['alice', 'bob'])
        with self.assertRaises(ValueError):
            parse_users('alice:2')

    async def test_failure_does_not_block_other_user(self):
        async def request(path, method='GET'):
            if path == 'users/alice':
                raise RuntimeError('failed')
            return {'servers': {'': {'ready': True}}}
        log = Mock()
        sleep = AsyncMock(side_effect=asyncio.CancelledError)
        with self.assertRaises(asyncio.CancelledError):
            await run(['alice', 'bob'], request, log, sleep)
        log.info.assert_called_once_with('JupyterExcel user server ready: %s', 'bob')
        log.warning.assert_called_once()
        sleep.assert_awaited_once_with(30)
