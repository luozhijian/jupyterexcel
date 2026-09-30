import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import nbformat
from nbformat.sign import NotebookNotary
from jupyter_server.services.contents.filemanager import FileContentsManager
from jupyter_server.services.kernels.kernelmanager import AsyncMappingKernelManager
from jupyter_server.services.sessions.sessionmanager import SessionManager
from jupyterexcel.kernel_pool import KernelPoolExecutor


class PoolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_pool_concurrency_reload_and_cleanup(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'IPYTHONDIR':root}):
            cm = FileContentsManager(root_dir=root, notary=NotebookNotary(data_dir=root))
            cm.save({'type':'file', 'format':'text', 'content':json.dumps({'execution':{'min_kernels':2,'max_kernels':2}})}, 'jupyterexcel-config.json')
            def notebook(offset):
                return nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(
                    'from jupyterexcel import jupyter_function\nimport os, time\n'
                    '@jupyter_function(name="Worker")\ndef worker(delay):\n'
                    f'    time.sleep(delay)\n    return [os.getpid(), {offset}]')])
            cm.save({'type':'notebook', 'content':notebook(1)}, 'functions.ipynb')
            km = AsyncMappingKernelManager(root_dir=root, connection_dir=root)
            sm = SessionManager(kernel_manager=km, contents_manager=cm)
            pool = KernelPoolExecutor(km, sm, cm, 'test', timeout=10)
            try:
                await pool.start()
                async with asyncio.timeout(30):
                    while len(pool.workers) != 2 or any(w.state != 'idle' for w in pool.workers):
                        await asyncio.sleep(.05)
                results = await asyncio.gather(pool.execute('Worker', [.3]), pool.execute('Worker', [.3]))
                self.assertTrue(all(r['ok'] for r in results))
                self.assertEqual(len({r['result'][0] for r in results}), 2)
                clients = [w.engine.connection.client for w in pool.workers]
                sockets = [c._shell_channel.socket for c in clients]
                repeated = await asyncio.gather(*(pool.execute('Worker', [0]) for _ in range(100)))
                self.assertTrue(all(r['ok'] for r in repeated))
                self.assertEqual([w.engine.connection.client for w in pool.workers], clients)
                self.assertEqual([c._shell_channel.socket for c in clients], sockets)
                for client in clients:
                    self.assertIsNone(client._hb_channel)
                    self.assertIsNone(client._iopub_channel)
                    self.assertIsNone(client._stdin_channel)
                    self.assertIsNone(client._control_channel)
                cm.save({'type':'notebook', 'content':notebook(2)}, 'functions.ipynb')
                await pool.reload_notebook('functions.ipynb')
                self.assertTrue(all(socket.closed for socket in sockets))
                result = await pool.execute('Worker', [0])
                self.assertEqual(result['result'][1], 2)
            finally:
                await pool.stop()
                self.assertEqual(await sm.list_sessions(), [])
                await km.shutdown_all(now=True)
                cm.notary.store.close()
                sm.close()
