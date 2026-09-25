import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jupyterexcel import jupyter_function, utils
from jupyterexcel.assets import AssetStore
from jupyterexcel.execution import invoke_export
from jupyterexcel.office_addin import scan_notebook, functions_metadata, functions_javascript, discover_notebooks


class FunctionNameTests(unittest.IsolatedAsyncioTestCase):
    def notebook(self, source):
        return {'cells': [{'cell_type': 'code', 'source': source}]}

    def contents(self, source):
        def get(path, content=True):
            if not path:
                return {'type': 'directory', 'content': [{'type': 'notebook', 'path': 'names.ipynb'}]}
            return {'type': 'notebook', 'path': path, 'content': self.notebook(source)}
        return SimpleNamespace(get=get)

    def test_decorator_scanner_and_javascript_preserve_spelling(self):
        for decorator, expected in (
            ('@jupyter_function', 'underscore_join'),
            ('@jupyter_function()', 'underscore_join'),
            ('@jupyter_function(name="My_Join")', 'My_Join'),
            ('@jupyter_function(name="string.join")', 'string.join'),
        ):
            with self.subTest(decorator=decorator), patch.dict(utils.jupyterexcel_functions, clear=True):
                source = decorator + '\ndef underscore_join(a, b): return a + b'
                scope = {'jupyter_function': jupyter_function}
                exec(source, scope)
                runtime = scope['underscore_join'].__jupyterexcel_function__
                functions = scan_notebook(self.notebook(source), 'names.ipynb')
                metadata = functions_metadata(functions)['functions'][0]
                for item in (runtime, metadata):
                    self.assertEqual(item['id'], expected)
                    self.assertEqual(item['name'], expected)
                script = functions_javascript(functions, 'https://example.com')
                self.assertIn('CustomFunctions.associate(' + json.dumps(expected), script)
                self.assertIn('/Excel/' + expected, script)

    def test_dotted_and_underscored_functions_execute_independently(self):
        with patch.dict(utils.jupyterexcel_functions, clear=True):
            @jupyter_function(name='string.join')
            def dotted(): return 'dot'
            @jupyter_function
            def string_join(): return 'underscore'
            with patch('IPython.get_ipython', return_value=SimpleNamespace(user_ns={'a': dotted, 'b': string_join})):
                for name, result in [('string.join', 'dot'), ('string_join', 'underscore'), ('STRING_JOIN', 'underscore')]:
                    self.assertEqual(json.loads(invoke_export(name, [])), {'ok': True, 'result': result})

    async def test_discovery_allows_punctuation_distinction_but_rejects_case_duplicates(self):
        for second, duplicate in [('string_join', False), ('STRING.JOIN', True)]:
            source = '@jupyter_function(name="string.join")\ndef a(): return 1\n@jupyter_function(name=' + repr(second) + ')\ndef b(): return 2'
            contents = self.contents(source)
            with tempfile.TemporaryDirectory() as directory:
                store = AssetStore(SimpleNamespace(contents_manager=contents), output_dir=directory)
                if duplicate:
                    with self.assertRaises(ValueError):
                        await store.discover()
                    with self.assertRaises(ValueError):
                        discover_notebooks(contents)
                else:
                    self.assertEqual([f.function_id for f in await store.discover()], ['string.join', 'string_join'])
                    self.assertEqual(len(discover_notebooks(contents)), 2)

    def test_kernel_rejects_case_only_duplicates(self):
        with patch.dict(utils.jupyterexcel_functions, clear=True):
            @jupyter_function(name='My_Join')
            def first(): return 1
            @jupyter_function(name='my_join')
            def second(): return 2
            with patch('IPython.get_ipython', return_value=SimpleNamespace(user_ns={'a': first, 'b': second})):
                self.assertEqual(json.loads(invoke_export('My_Join', []))['error']['code'], 'duplicate_function')

    def test_invalid_names_are_rejected_instead_of_renamed(self):
        for name in ('', 'bad name', 'bad-name', 'bad/name'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    jupyter_function(name=name)(lambda: None)
                source = '@jupyter_function(name=' + repr(name) + ')\ndef sample(): return 1'
                with self.assertRaises(ValueError):
                    functions_metadata(scan_notebook(self.notebook(source), 'names.ipynb'))
