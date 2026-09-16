import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jupyterexcel import ribbon_function, jupyter_function
from jupyterexcel.actions import action_schema, validate_inputs, validate_result
from jupyterexcel.action_examples import group_sum_by_color
from jupyterexcel.office_addin import scan_notebook, functions_metadata
from jupyterexcel.execution import invoke_action, invoke_export, SharedKernelExecutor

META = {'data': {'source': 'range', 'type': 'matrix', 'read': ['values', 'fillColors']}}


class ActionTests(unittest.TestCase):
    def test_static_discovery_is_separate_and_literal(self):
        source = '@ribbon_function(name="COLORS", inputs=' + repr(META) + ')\ndef colors(data):\n raise RuntimeError("must not execute")'
        found = scan_notebook({'cells': [{'cell_type': 'code', 'source': source}]}, 'nested/demo.ipynb')
        self.assertEqual(found[0].action['button_text'], 'Run')
        self.assertEqual(found[0].notebook, 'nested/demo.ipynb')
        self.assertEqual(functions_metadata(found)['functions'], [])
        with self.assertRaises(ValueError):
            scan_notebook({'cells': [{'cell_type': 'code', 'source': source.replace(repr(META), 'get_inputs()')}]}, 'bad.ipynb')

    def test_separate_resolvers_and_validation(self):
        @ribbon_function(name='COLORS', inputs=META)
        def colors(data):
            return group_sum_by_color(data)
        @jupyter_function(name='COLORS')
        def worksheet(data):
            return 'worksheet'
        data = {'values': [[10, True, 'text'], [30, 20, 5]],
                'format': {'fillColors': [['#FFFF00', '', ''], ['#FFFF00', '#FFFFFF', '']]}}
        with patch('IPython.get_ipython', return_value=SimpleNamespace(user_ns={'action': colors, 'formula': worksheet})):
            response = json.loads(invoke_action('COLORS', [data]))
            self.assertTrue(response['ok'])
            self.assertEqual(response['result']['result']['values'][1:], [[2, 40], [1, 20], [1, 5]])
            self.assertEqual(json.loads(invoke_export('COLORS', [data], action=False))['result'], 'worksheet')
            self.assertEqual(json.loads(invoke_action('COLORS', []))['error']['code'], 'invalid_arguments')
            self.assertEqual(json.loads(invoke_action('MISSING', [data]))['error']['code'], 'function_not_found')
        self.assertEqual(colors(data)['result']['values'][-1], [1, 5])
        self.assertEqual(colors(data)['result']['format']['fillColors'], [[None, None], ['#FFFF00', '#FFFF00'], ['#FFFFFF', '#FFFFFF'], ['', '']])

    def test_invalid_dimensions_colors_and_schema(self):
        schema = action_schema('COLORS', META)
        for data in ({'values': [[1]], 'fillColors': [[None, None]]},
                     {'values': [[1]], 'fillColors': [['red']]},
                     {'values': [[1]], 'fillColors': [[None]], 'code': 'x'}):
            with self.assertRaises(ValueError): validate_inputs(schema, [data])
        with self.assertRaises(ValueError): action_schema('BAD', {'x': {'source': 'range', 'type': 'matrix', 'read': ['formulas']}})
        with self.assertRaises(ValueError): validate_result(schema, {'result': [[1]], 'updates': {'unknown': {'values': [[3]]}}})

    def test_one_to_many_parameters_and_repeatable_values(self):
        for count in (0, 1, 2, 4):
            schema = action_schema('A', {f'x{i}': {'source': 'value', 'type': 'number'} for i in range(count)})
            validate_inputs(schema, list(range(count)))
        schema = action_schema('A', {'items': {'source': 'value', 'type': 'number', 'repeatable': True}})
        validate_inputs(schema, [[1,2,3]])
        with self.assertRaises(ValueError): validate_inputs(schema, [['text']])

    def test_legacy_decorator_stays_available(self):
        @ribbon_function('Legacy', 'D2', a='A2')
        def legacy(a): return a
        self.assertEqual(legacy(3), 3)
        self.assertFalse(hasattr(legacy, '__jupyterexcel_action__'))

    def test_roundtrip_block_and_null_semantics(self):
        from jupyterexcel.actions import validate_block
        data = {'values': [[1, 2]], 'format': {'fillColors': [['#FFFF00', '']]}}
        validate_inputs(action_schema('A', META), [data])
        validate_result(action_schema('A', META), {'result': data})
        preserved = {'values': [[1]], 'format': {'fillColors': [[None]]}}
        validate_block(preserved)
        with self.assertRaises(ValueError): validate_block(preserved, input_block=True)
        with self.assertRaises(ValueError): validate_block({'values': [[1]], 'format': {'fillColors': [['', '']]}})
        schema = action_schema('A', {'data': {'source': 'cell', 'type': 'number', 'read': ['values', 'format.fillColors']}})
        validate_inputs(schema, [{'values': [[1]], 'format': {'fillColors': [['']]}}])
        with self.assertRaises(ValueError): validate_inputs(schema, [data])

    def test_unified_resolution_rejects_collisions(self):
        @ribbon_function(name='SAME', inputs={}, output={'type':'number'})
        def action(): return {'result': 1}
        @jupyter_function(name='SAME')
        def formula(): return 2
        with patch('IPython.get_ipython', return_value=SimpleNamespace(user_ns={'a':action,'f':formula})):
            self.assertEqual(json.loads(invoke_export('SAME', []))['error']['code'], 'duplicate_function')
        with patch('IPython.get_ipython', return_value=SimpleNamespace(user_ns={'a':action})):
            self.assertEqual(json.loads(invoke_export('SAME', []))['result'], {'result':1})
            self.assertEqual(json.loads(invoke_export('SAME', [], action=False))['error']['code'], 'function_not_found')

    def test_empty_numeric_selection_is_clear(self):
        with self.assertRaisesRegex(ValueError, 'no numeric'):
            group_sum_by_color({'values': [['x', True]], 'format': {'fillColors': [['', '']]}})


class ActionNotebookTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_kernel_action_initialization_and_isolation(self):
        from jupyter_client import AsyncKernelManager
        from unittest.mock import AsyncMock
        from pathlib import Path
        import tempfile
        import os
        km = AsyncKernelManager()
        with tempfile.TemporaryDirectory() as directory:
            await km.start_kernel(cwd=str(Path(__file__).resolve().parents[1]), env=dict(os.environ, IPYTHONDIR=directory))
            try:
                source = 'from jupyterexcel import ribbon_function\ncount = globals().get("count",0)+1\n@ribbon_function(name="ACTION", inputs={"x":{"type":"number"}},output={"type":"number"})\ndef a(x): return {"result": x+count}'
                models = {'': {'type':'directory','content':[{'type':'notebook','path':'a.ipynb'}]},
                          'a.ipynb': {'type':'notebook','content':{'cells':[{'cell_type':'code','source':source}]}}}
                manager = SimpleNamespace(list_kernels=lambda:[{'id':'one','execution_state':'idle'}],get_kernel=lambda key:km)
                sessions = SimpleNamespace(list_sessions=lambda:[],create_session=AsyncMock(return_value={'kernel':{'id':'one'}}))
                executor = SharedKernelExecutor(manager,sessions,SimpleNamespace(get=lambda path,content:models[path]),'alice')
                for _ in range(2):
                    self.assertEqual(await executor.execute('ACTION',[3]),{'ok':True,'result':{'result':4}})
                self.assertEqual((await executor.execute('ACTION',[3],action=False))['error']['code'],'function_not_found')
            finally:
                await km.shutdown_kernel(now=True)

    async def test_demo_generates_action_catalog(self):
        from pathlib import Path
        import tempfile
        import logging
        from jupyterexcel.assets import AssetStore
        import xml.etree.ElementTree as ET
        notebook = json.loads((Path(__file__).resolve().parents[1]/'examples/SumGroupByColor.ipynb').read_text())
        class Contents:
            async def get(self,path,content=True):
                if not path: return {'type':'directory','content':[{'type':'notebook','path':'demo.ipynb'}]}
                return {'type':'notebook','path':path,'content':notebook}
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(contents_manager=Contents(),log=logging.getLogger('test'),web_app=SimpleNamespace(settings={'base_url':'/'}),port=8888)
            store = AssetStore(app,output_dir=directory,asset_url='https://assets.example/addin')
            await store.generate()
            catalog=json.loads((Path(directory)/'actions.json').read_text())
            self.assertEqual(catalog['actions'][0]['id'],'SUM.GROUP.BY.COLOR')
            self.assertEqual(catalog['actions'][0]['button_text'],'Calculate')
            self.assertEqual({f['id'] for f in json.loads((Path(directory)/'functions.json').read_text())['functions']},
                             {'MANIFESTURL', 'SERVERURL', 'ADDINVERSION', 'ASSETVERSION'})
            manifest=ET.parse(Path(directory)/'manifest.xml')
            panes=[e for e in manifest.iter() if e.attrib.get('resid')=='Taskpane.Url']
            self.assertTrue(panes)
            self.assertIn('id="notebook-actions"', (Path(directory)/'taskpane.html').read_text())
            self.assertTrue((Path(directory)/'actions.js').is_file())

    async def test_action_only_notebook_initializes(self):
        source = '@ribbon_function(name="A", inputs={})\ndef a(): return {"result": [[1]]}'
        class Contents:
            async def get(self, path, content=True):
                if not path: return {'type': 'directory', 'content': [{'type': 'notebook','path':'nested/actions.ipynb'}]}
                return {'type': 'notebook', 'content': {'cells': [{'cell_type':'code','source':source}]}}
        executor = SharedKernelExecutor(None, None, Contents(), 'alice')
        self.assertEqual((await executor._notebooks())[0][0], 'nested/actions.ipynb')


from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application
from jupyter_server.auth.identity import IdentityProvider, User
from jupyterexcel.server_extension import ExcelModeHandler


class ActionIdentity(IdentityProvider):
    async def get_user(self,handler):
        authenticated=handler.request.headers.get('Authorization') == 'token test'
        handler._token_authenticated=authenticated
        return User(username='alice') if authenticated else None


class ActionHTTPTests(AsyncHTTPTestCase):
    def get_app(self):
        class Executor:
            async def execute(self,name,args,**kwargs):
                return {'ok': True,'result': {'action':kwargs.get('action'), 'args':args}}
        return Application([
            (r'/user/alice/Excel/(.*)',ExcelModeHandler,{'executor':Executor(),'hub_user':'alice'}),
            (r'/user/bob/Excel/(.*)',ExcelModeHandler,{'executor':Executor(),'hub_user':'bob'}),
        ],identity_provider=ActionIdentity(),cookie_secret='test')

    def test_post_auth_owner_and_read_only_get(self):
        headers={'Authorization':'token test','Content-Type':'application/json'}
        url='/user/alice/Excel/A'
        response=self.fetch(url,method='POST',headers=headers,body='[3]')
        self.assertEqual(response.code,200)
        self.assertIsNone(json.loads(response.body)['result']['action'])
        self.assertEqual(self.fetch(url,headers=headers).code,400)
        self.assertIn(self.fetch(url,method='POST',headers={'Content-Type':'application/json'},body='[]').code,(401,403))
        self.assertEqual(self.fetch('/user/bob/Excel/A',method='POST',headers=headers,body='[]').code,403)
        self.assertEqual(self.fetch(url,method='POST',headers=headers,body='{}').code,400)


if __name__ == '__main__': unittest.main()
