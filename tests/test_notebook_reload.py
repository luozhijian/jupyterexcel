import asyncio
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application
from jupyter_server.auth.identity import IdentityProvider, User
from jupyterexcel.execution import SharedKernelExecutor, ExecutionError
from jupyterexcel.reload_handler import ReloadNotebookHandler


class Identity(IdentityProvider):
    async def get_user(self, handler):
        token = handler.request.headers.get('Authorization')
        handler._token_authenticated = bool(token)
        name = token.removeprefix('token ') if token else handler.get_cookie('test-login')
        return User(username=name) if name else None


class Handler(ReloadNotebookHandler):
    async def get(self):
        self.finish({'xsrf': self.xsrf_token.decode()})


class ReloadHTTPTests(AsyncHTTPTestCase):
    def get_app(self):
        self.events = []
        async def generate():
            self.events.append('assets')
            return False
        async def reload(path):
            self.events.append(path)
            return 'kernel'
        self.store = SimpleNamespace(generate=AsyncMock(side_effect=generate), current='version')
        self.executor = SimpleNamespace(contents=SimpleNamespace(get=AsyncMock(return_value={'type':'notebook'})),
                                        reload_notebook=AsyncMock(side_effect=reload))
        self.authorizer = SimpleNamespace(is_authorized=AsyncMock(return_value=True))
        return Application([(r'/user/alice/jupyterexcel/api/reload', Handler,
                            dict(executor=self.executor, store=self.store, hub_user='alice'))],
                           identity_provider=Identity(), authorizer=self.authorizer,
                           cookie_secret='test', xsrf_cookies=True, login_url='/login')

    def post(self, path='nested/book.ipynb', headers=None):
        return self.fetch('/user/alice/jupyterexcel/api/reload', method='POST',
                          headers=headers or {'Authorization':'token alice', 'Content-Type':'application/json'},
                          body=json.dumps({'path':path}))

    def test_unchanged_assets_still_reload_in_order(self):
        response = self.post()
        self.assertEqual(response.code, 200)
        self.assertEqual(self.events, ['assets', 'nested/book.ipynb'])
        self.assertFalse(json.loads(response.body)['assets_changed'])

    def test_auth_owner_authorization_and_paths(self):
        for headers in ({'Content-Type':'application/json'},
                        {'Content-Type':'application/json','Authorization':'token bob'}):
            self.assertEqual(self.post(headers=headers).code, 403)
        for path in ('../secret.ipynb', '/root.ipynb', 'a\\b.ipynb', 'a/../b.ipynb', 'x.txt'):
            self.assertEqual(self.post(path).code, 400)
        self.authorizer.is_authorized.return_value = False
        self.assertEqual(self.post().code, 403)
        self.executor.reload_notebook.assert_not_awaited()

    def test_cookie_login_requires_xsrf(self):
        headers = {'Content-Type':'application/json', 'Cookie':'test-login=alice'}
        self.assertEqual(self.post(headers=headers).code, 403)
        response = self.fetch('/user/alice/jupyterexcel/api/reload', headers={'Cookie':'test-login=alice'})
        token = json.loads(response.body)['xsrf']
        headers['Cookie'] += '; _xsrf=' + token
        headers['X-XSRFToken'] = token
        self.assertEqual(self.post(headers=headers).code, 200)

    def test_generation_error_prevents_execution(self):
        self.store.generate.side_effect = OSError('test failure')
        self.assertEqual(self.post().code, 500)
        self.executor.reload_notebook.assert_not_awaited()


class ReloadKernelTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_kernel_times_out_without_interrupt(self):
        manager = SimpleNamespace(list_kernels=lambda:[{'id':'one', 'execution_state':'busy'}])
        executor = SharedKernelExecutor(manager, None, None, 'alice', timeout=0.01)
        executor.kernel_id = 'one'
        executor._initialize = AsyncMock()
        with self.assertRaises(ExecutionError) as result:
            await executor.reload_notebook('a.ipynb')
        self.assertEqual(result.exception.code, 'kernel_busy')
        executor._initialize.assert_not_awaited()
        self.assertFalse(executor.lock.locked())

    async def test_real_reload_cold_once_warm_selected_and_failure(self):
        from jupyter_client import AsyncKernelManager
        km = AsyncKernelManager()
        with tempfile.TemporaryDirectory() as directory:
            await km.start_kernel(cwd=str(Path(__file__).resolve().parents[1]),
                                  env=dict(os.environ, IPYTHONDIR=directory))
            try:
                source = 'from jupyterexcel import jupyter_function\ncount = globals().get("count",0)+1\n@jupyter_function(name="ADD")\ndef add(): return [count, other]'
                other = 'other=globals().get("other",0)+1\n@jupyter_function(name="OTHER")\ndef other_value(): return other'
                def notebook(code):
                    return {'type':'notebook','content':{'cells':[{'cell_type':'code','source':code}]}}
                models = {'':{'type':'directory','content':[{'type':'directory','path':'nested'}]},
                          'nested':{'type':'directory','content':[{'type':'notebook','path':'nested/a.ipynb'}, {'type':'notebook','path':'nested/b.ipynb'}]},
                          'nested/a.ipynb':notebook(source), 'nested/b.ipynb':notebook(other)}
                manager = SimpleNamespace(list_kernels=lambda:[{'id':'one','execution_state':'idle'}], get_kernel=lambda key:km)
                sessions = SimpleNamespace(list_sessions=lambda:[], create_session=AsyncMock(return_value={'kernel':{'id':'one'}}))
                executor = SharedKernelExecutor(manager, sessions, SimpleNamespace(get=lambda path,content:models[path]), 'alice')
                await executor.reload_notebook('nested/a.ipynb')
                self.assertEqual((await executor.execute('ADD', []))['result'], [1,1])
                models['nested/a.ipynb'] = notebook(source.replace('[count, other]', '[count*10, other]'))
                await executor.reload_notebook('nested/a.ipynb')
                self.assertEqual((await executor.execute('ADD', []))['result'], [20,1])
                models['nested/a.ipynb']['content']['cells'].append({'cell_type':'code','source':'raise ValueError("bad")'})
                with self.assertRaises(ExecutionError) as result:
                    await executor.reload_notebook('nested/a.ipynb')
                self.assertIn('nested/a.ipynb, cell 2', str(result.exception))
                self.assertFalse(executor.lock.locked())
            finally:
                await km.shutdown_kernel(now=True)
