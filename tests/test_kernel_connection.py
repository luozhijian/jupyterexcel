import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from jupyterexcel.kernel_connection import KernelConnection


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    def fake(self, fail=False):
        class Client:
            def __init__(self):
                self._shell_channel = None
                self.messages = asyncio.Queue()
                self.starts = []
            def load_connection_info(self, info):
                pass
            def start_channels(self, **kwargs):
                self.starts.append(kwargs)
                self._shell_channel = SimpleNamespace(close=Mock())
                if fail:
                    raise RuntimeError('partial startup')
            def kernel_info(self):
                self.messages.put_nowait({'parent_header': {'msg_id':'old'}, 'header': {'msg_type':'kernel_info_reply'}})
                self.messages.put_nowait({'parent_header': {'msg_id':'ready'}, 'header': {'msg_type':'kernel_info_reply'}})
                return 'ready'
            async def get_shell_msg(self):
                return await self.messages.get()
        return Client

    async def test_thousands_of_acquisitions_reuse_one_socket_and_no_heartbeat(self):
        kernel = SimpleNamespace(get_connection_info=lambda: {'key':b'test', 'shell_port':123}, provisioner=SimpleNamespace(pid=1))
        connection = KernelConnection()
        with patch('jupyter_client.AsyncKernelClient', side_effect=self.fake()) as factory:
            first = connection.open(kernel)
            await connection.wait_for_ready(1)
            for _ in range(2000):
                self.assertIs(connection.open(kernel), first)
                await connection.wait_for_ready(1)
            factory.assert_called_once()
            self.assertEqual(first.starts, [dict(shell=True, iopub=False, stdin=False, hb=False, control=False)])
            connection.close()
            connection.close()
            first._shell_channel.close.assert_called_once()

    async def test_restart_replaces_socket_even_when_ports_are_unchanged(self):
        kernel = SimpleNamespace(get_connection_info=lambda: {'shell_port':123}, provisioner=SimpleNamespace(pid=1))
        connection = KernelConnection()
        with patch('jupyter_client.AsyncKernelClient', side_effect=self.fake()):
            old = connection.open(kernel)
            await connection.wait_for_ready(1)
            kernel.provisioner.pid = 2
            self.assertIsNot(connection.open(kernel), old)
            self.assertFalse(connection.ready)
            old._shell_channel.close.assert_called_once()
            connection.close()

    async def test_partial_startup_closes_created_socket(self):
        client = self.fake(fail=True)()
        connection = KernelConnection()
        with patch('jupyter_client.AsyncKernelClient', return_value=client):
            with self.assertRaisesRegex(RuntimeError, 'partial startup'):
                connection.open(SimpleNamespace(get_connection_info=lambda: {}))
        client._shell_channel.close.assert_called_once()
        self.assertIsNone(connection.client)
