import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from traitlets.config import Config
from jupyterexcel.hub_autostart import configure_autostart, ensure_server, parse_users, run


class AutostartTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_service_preserves_existing_hook(self):
        import json
        import tempfile
        from pathlib import Path
        config = Config()
        previous = AsyncMock()
        config.Spawner.pre_spawn_hook = previous
        config.JupyterHub.services = [{'name': 'existing'}]
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'settings.json'
            file.write_text(json.dumps({'server': {'public_url': 'https://api.example'},
                'assets': {'directory': directory, 'url': 'https://assets.example'},
                'hub': {'auto_start_users': ['alice', 'bob']}}))
            configure_autostart(config, str(file))
            self.assertEqual(len(config.JupyterHub.services), 2)
            self.assertEqual(config.JupyterHub.services[1]['environment'],
                             {'JUPYTEREXCEL_CONFIG_FILE': str(file.resolve())})
            self.assertEqual(config.JupyterHub.load_roles[0]['scopes'],
                ['read:servers!user=alice', 'servers!user=alice',
                 'read:servers!user=bob', 'servers!user=bob'])
            self.assertIs(config.Spawner.pre_spawn_hook, previous)
            with self.assertRaisesRegex(ValueError, 'already configured'):
                configure_autostart(config, str(file))

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
        from unittest.mock import patch
        with patch('jupyterexcel.hub_autostart.load_config', return_value={'config': {'hub': {'auto_start_users': []}}}):
            configure_autostart(config)
        self.assertEqual(dict(config), {})
        self.assertEqual(parse_users(['alice', 'bob', 'alice']), ['alice', 'bob'])
        with self.assertRaises(ValueError):
            parse_users(['alice:2'])

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
