import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from jupyterexcel.execution import SharedKernelExecutor


class SharedKernelTests(unittest.IsolatedAsyncioTestCase):
    async def test_name_reuse_and_replacement(self):
        models = []
        sessions = []
        async def create_session(**kwargs):
            model = dict(kwargs, kernel={'id': str(len(sessions) + 1)})
            sessions.append(model)
            models.append({'id': model['kernel']['id']})
            return model
        manager = SimpleNamespace(list_kernels=lambda: models)
        sm = SimpleNamespace(list_sessions=lambda: sessions, create_session=create_session)
        executor = SharedKernelExecutor(manager, sm, None, 'alice')
        self.assertEqual(await executor._ensure_kernel(), '1')
        self.assertEqual(sessions[0]['name'], 'JupyterExcel - alice - 1')
        self.assertEqual(await executor._ensure_kernel(), '1')
        models.clear()
        self.assertEqual(await executor._ensure_kernel(), '2')
        self.assertEqual(sessions[1]['name'], 'JupyterExcel - alice - 2')

    async def test_real_kernel_loading_reuse_and_restart(self):
        from jupyter_client import AsyncKernelManager
        from pathlib import Path
        import tempfile
        import os
        km = AsyncKernelManager()
        with tempfile.TemporaryDirectory() as directory:
            await km.start_kernel(cwd=str(Path(__file__).resolve().parents[1]),
                                  env=dict(os.environ, IPYTHONDIR=directory))
            try:
                source = 'from jupyterexcel import jupyter_function\ncount = globals().get("count", 0) + 1\n@jupyter_function(name="ADD")\ndef add(a, b): return a + b + count'
                notebook = {'type': 'notebook', 'content': {'cells': [{'cell_type': 'code', 'source': source}]}}
                models = {'': {'type': 'directory', 'content': [{'type': 'directory', 'path': 'nested'}]},
                          'nested': {'type': 'directory', 'content': [{'type': 'notebook', 'path': 'nested/a.ipynb'}]},
                          'nested/a.ipynb': notebook}
                manager = SimpleNamespace(list_kernels=lambda: [{'id': 'one', 'execution_state': 'idle'}], get_kernel=lambda key: km)
                sm = SimpleNamespace(list_sessions=lambda: [], create_session=AsyncMock(return_value={'kernel': {'id': 'one'}}))
                cm = SimpleNamespace(get=lambda path, content: models[path])
                executor = SharedKernelExecutor(manager, sm, cm, 'alice')
                for _ in range(2):
                    self.assertEqual(await executor.execute('ADD', [2, 3]), {'ok': True, 'result': 6})
                sm.create_session.assert_awaited_once()
                await km.restart_kernel(now=True)
                self.assertEqual(await executor.execute('ADD', [2, 3]), {'ok': True, 'result': 6})
            finally:
                await km.shutdown_kernel(now=True)

    async def test_actual_server_session_startup(self):
        import tempfile
        import os
        from unittest.mock import patch
        import nbformat
        from jupyter_server.services.kernels.kernelmanager import AsyncMappingKernelManager
        from jupyter_server.services.sessions.sessionmanager import SessionManager
        from jupyter_server.services.contents.filemanager import FileContentsManager
        from nbformat.sign import NotebookNotary
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'IPYTHONDIR': root}):
            cm = FileContentsManager(root_dir=root, notary=NotebookNotary(data_dir=root))
            cm.save({'type': 'notebook', 'content': nbformat.v4.new_notebook(cells=[
                nbformat.v4.new_code_cell('from jupyterexcel import jupyter_function\n@jupyter_function(name="ADD")\ndef add(a,b): return a+b')])}, 'example.ipynb')
            km = AsyncMappingKernelManager(root_dir=root, connection_dir=root)
            sm = SessionManager(kernel_manager=km, contents_manager=cm)
            try:
                executor = SharedKernelExecutor(km, sm, cm, 'alice')
                # Startup initialization happens before any Excel function request.
                self.assertTrue(await executor.ensure_ready())
                first_id = executor.kernel_id
                self.assertTrue(await executor.ensure_ready())
                self.assertEqual(executor.kernel_id, first_id)
                await km.shutdown_kernel(first_id, now=True)
                self.assertTrue(await executor.ensure_ready())
                self.assertNotEqual(executor.kernel_id, first_id)

                self.assertEqual(await executor.execute('ADD', [2, 3]), {'ok': True, 'result': 5})
                sessions = await sm.list_sessions()
                self.assertEqual(sessions[-1]['name'], 'JupyterExcel - alice - 2')
            finally:
                await km.shutdown_all(now=True)
                cm.notary.store.close()
                sm.close()
