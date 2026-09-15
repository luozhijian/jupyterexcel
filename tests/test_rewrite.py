import asyncio
import os
import json
import logging
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application
from jupyterexcel.assets import AssetStore, version_stamp
from jupyterexcel.execution import KernelExecutor, ExecutionError
from jupyterexcel.server_extension import ExcelModeHandler
from jupyter_server.auth.identity import IdentityProvider, User


class TestIdentity(IdentityProvider):
    async def get_user(self, handler):
        handler._token_authenticated = bool(handler.request.headers.get('Authorization'))
        return User(username='alice')


TestHandler = ExcelModeHandler


class FakeExecutor:
    async def execute(self, name, inputs, idle_only=False, **kwargs):
        return {'ok': True, 'result': [name, inputs, idle_only]}


class HTTPTests(AsyncHTTPTestCase):
    def get_app(self):
        return Application([
            (r'/Excel/(.*)', TestHandler, {'executor': FakeExecutor()}),
            (r'/hub/(.*)', TestHandler, {'executor': FakeExecutor(), 'hub_user': 'alice'}),
            (r'/other/(.*)', TestHandler, {'executor': FakeExecutor(), 'hub_user': 'bob'}),
        ], cookie_secret='test', identity_provider=TestIdentity())

    def test_get_post_arrays_and_errors(self):
        get = self.fetch('/Excel/ADD?params=%5B%5B3,4%5D%5D')
        post = self.fetch('/Excel/ADD', method='POST', headers={'Content-Type': 'application/json', 'Authorization': 'token dummy'}, body='[[3,4]]')
        self.assertEqual(get.code, 200)
        self.assertEqual(json.loads(get.body), json.loads(post.body))
        for payload in ('{}', 'null', '[NaN]', 'bad'):
            response = self.fetch('/Excel/ADD', method='POST', headers={'Content-Type': 'application/json', 'Authorization': 'token dummy'}, body=payload)
            self.assertEqual(response.code, 400)
        self.assertEqual(self.fetch('/Excel/ADD').code, 400)

    def test_get_requires_params(self):
        legacy = self.fetch('/Excel/ADD?inputs=[1,2]')
        self.assertEqual(legacy.code, 400)
        self.assertEqual(json.loads(legacy.body)['error']['code'], 'params')
        preferred = self.fetch('/Excel/ADD?params=[1,2]')
        self.assertEqual(preferred.code, 200)

    def test_hub_header_and_owner(self):
        self.assertEqual(self.fetch('/hub/ADD?params=[]').code, 401)
        headers = {'Authorization': 'token dummy'}
        self.assertEqual(self.fetch('/hub/ADD?params=[]', headers=headers).code, 200)
        self.assertEqual(self.fetch('/other/ADD?params=[]', headers=headers).code, 403)


class Contents:
    async def get(self, path, content=True):
        if not path:
            return {'type': 'directory', 'content': [{'type': 'notebook', 'path': 'nested/a.ipynb'}]}
        return {'type': 'notebook', 'path': path, 'content': {'cells': [{'cell_type': 'code', 'source': '@jupyter_function(name="ADD")\ndef add(a,b=0):\n return a+b'}]}}


class AssetTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_contents_save_generates_assets(self):
        from jupyter_server.services.contents.filemanager import FileContentsManager
        import nbformat
        with tempfile.TemporaryDirectory() as directory:
            from nbformat.sign import NotebookNotary
            cm = FileContentsManager(root_dir=directory, notary=NotebookNotary(data_dir=directory))
            app = SimpleNamespace(contents_manager=cm, log=logging.getLogger('test'), web_app=SimpleNamespace(settings={'base_url':'/'}), port=8888)
            store = AssetStore(app, output_dir=Path(directory)/'data'/'excel-addin', asset_url='https://assets.example/excel-addin')
            cm.register_post_save_hook(store.schedule)
            notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell('@jupyter_function\ndef saved(a): return a')])
            cm.save({'type':'notebook','content':notebook}, 'saved.ipynb')
            await store.task
            self.assertEqual(json.loads(store.resolve('functions.json').read_text())['functions'][0]['id'], 'SAVED')
            cm.notary.store.close()

    async def test_save_hook_keeps_existing_registration(self):
        from jupyterexcel.server_extension import load_jupyter_server_extension
        cm = Contents()
        hooks = [lambda **kwargs: None]
        cm.register_post_save_hook = hooks.append
        routes = []
        app = SimpleNamespace(contents_manager=cm, log=logging.getLogger('test'), kernel_manager=object(), session_manager=object(), web_app=SimpleNamespace(settings={'base_url': '/'}, add_handlers=lambda host, handlers: routes.extend(handlers)))
        with tempfile.TemporaryDirectory() as test_data, patch.dict(os.environ, {'JUPYTEREXCEL_ASSET_DIR':test_data}), patch.object(AssetStore, 'schedule') as schedule:
            load_jupyter_server_extension(app)
            self.assertEqual(len(hooks), 2)
            self.assertEqual(len(routes), 2)
            self.assertIn('/jupyterexcel/api/reload', routes[1][0])
            self.assertIn('/Excel/', routes[0][0])
            hooks[1](model={'type':'notebook'})
            self.assertEqual(schedule.call_count, 2)
            load_jupyter_server_extension(app)
            self.assertEqual(len(hooks), 2)

    async def test_generation_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(contents_manager=Contents(), log=logging.getLogger('test'), web_app=SimpleNamespace(settings={'base_url': '/user/alice/'}), port=8888)
            store = AssetStore(
                app,
                output_dir=Path(directory)/'excel-addin',
                username='alice',
                asset_url='https://www.jupyterexcel.com/excel-addin/',
            )
            await store.generate()
            self.assertEqual(store.root, Path(directory)/'excel-addin'/'alice')
            manifest = (store.root / 'manifest.xml').read_text()
            self.assertIn('https://www.jupyterexcel.com/excel-addin/alice/functions.js', manifest)
            self.assertNotIn('localhost', manifest)
            self.assertNotIn(store.current + '.js', manifest)
            self.assertNotIn('/user/alice/jupyterexcel/', manifest)
            self.assertNotIn('8888', manifest)
            self.assertTrue((store.root/'functions.json').is_file())
            self.assertTrue((store.root/'functions.js').is_file())
            from html.parser import HTMLParser
            class Scripts(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.sources = []
                def handle_starttag(self, tag, attrs):
                    if tag == 'script':
                        self.sources.append(dict(attrs).get('src', ''))
            for name in ('functions.html', 'commands.html', 'taskpane.html', 'token-dialog.html'):
                content = (store.root / name).read_text()
                self.assertNotIn('{{', content)
                parser = Scripts()
                parser.feed(content)
                for src in parser.sources:
                    if src and not src.startswith('https://'):
                        self.assertTrue((store.root / src).is_file(), src)
            self.assertIn('ShowDebugLogButton', manifest)
            self.assertIn('InputAccessTokenButton', manifest)
            self.assertIn('Worksheet functions', (store.root / 'taskpane.html').read_text())
            config = (store.root / 'jupyter-config.js').read_text()
            self.assertIn('"hubUser": "alice"', config)
            self.assertIn('http://localhost:8888/user/alice', config)

            self.assertEqual(json.loads(store.resolve('public/functions.json').read_text())['functions'][0]['id'], 'ADD')
            html = store.resolve('public/functions.html').read_text()
            self.assertIn('functions.js', html)
            self.assertNotIn('<base ', html)
            script = store.resolve('public/functions.js').read_text()
            self.assertIn('/user/alice/Excel/ADD', script)
            self.assertNotIn('CustomFunctions.associate("CLOCK"', script)
            with self.assertRaises(FileNotFoundError):
                store.resolve('../../../../setup.py')
            first = store.current
            (store.root/'versions'/'26AFE0509').mkdir()
            (store.root/'versions'/'26AFE0509'/'manifest.xml').write_text('incomplete')
            with self.assertRaises(FileNotFoundError):
                store.resolve('versions/26AFE0509/manifest.xml')
            await store.generate()
            self.assertEqual(first, store.current)
            self.assertTrue(store.resolve('versions/'+first+'/functions.js').exists())

    def test_timestamp(self):
        self.assertEqual(version_stamp(datetime(2026,10,15,14,5,9)), '20261015140509')
        self.assertEqual(version_stamp(datetime(2026,12,31,0,0,0)), '20261231000000')


class KernelTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_idle_kernel(self):
        manager = SimpleNamespace(list_kernels=lambda: [{'id':'one','execution_state':'busy'}])
        with self.assertRaises(ExecutionError) as caught:
            await KernelExecutor(manager).execute('ADD', [], idle_only=True)
        self.assertEqual(caught.exception.status, 503)

    async def test_real_kernel_types_defaults_and_errors(self):
        from jupyter_client import AsyncKernelManager
        km = AsyncKernelManager()
        import os
        env = dict(os.environ, IPYTHONDIR=tempfile.mkdtemp(prefix='jupyterexcel-ipython-'))
        await km.start_kernel(cwd=str(Path(__import__('jupyterexcel').__file__).parent.parent), env=env)
        client = km.client()
        client.start_channels()
        try:
            await client.wait_for_ready(timeout=30)
            msgid = client.execute('from jupyterexcel import jupyter_function\n@jupyter_function(name="ADD")\ndef add(a,b=2): return a+b\n@jupyter_function\ndef echo(value): return value\n@jupyter_function\ndef zero(): return None')
            while (await client.get_shell_msg(timeout=30))['parent_header']['msg_id'] != msgid:
                pass
            class Manager:
                def list_kernels(self):
                    return [{'id': 'one', 'execution_state': 'idle'}]
                def get_kernel(self, kernel_id):
                    return km
            executor = KernelExecutor(Manager())
            for name, args, expected in [('ADD',[3],5),('ECHO',[[3,4]],[3,4]),('ECHO',[{'x':True}],{'x':True}),('ZERO',[],None),('ECHO',["');raise Exception('injection')#"],"');raise Exception('injection')#")]:
                self.assertEqual(await executor.execute(name,args), {'ok':True,'result':expected})
            self.assertEqual((await executor.execute('ADD',[]))['error']['code'], 'invalid_arguments')
            self.assertEqual((await executor.execute('MISSING',[]))['error']['code'], 'function_not_found')
            self.assertEqual((await executor.execute('ADD',['x', 1]))['error']['code'], 'execution_failed')
            executor.reserved.add('one')
            with self.assertRaises(ExecutionError):
                await executor.execute('ADD',[1],idle_only=True)
        finally:
            client.stop_channels()
            await km.shutdown_kernel(now=True)


if __name__ == '__main__':
    unittest.main()
