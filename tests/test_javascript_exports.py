import asyncio
import json
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from jupyterexcel.office_addin import scan_notebook, functions_metadata, functions_javascript
from jupyterexcel.javascript_execution import JavaScriptExecutor
from jupyterexcel.execution import ExecutionError, SharedKernelExecutor
from jupyterexcel.assets import AssetStore

ADD = '''/** Adds two numbers.
 * @excelFunction JS_ADD
 * @execution local
 * @param {number} a First number.
 * @param {number} [b=0] Second number.
 * @returns {number} Sum.
 * @example =Jupyter.JS_ADD(3, 5)
 */
function add(a, b = 0) { return a + b; }
'''
ACTION = '''/** Formats a greeting.
 * @ribbonFunction JS_GREET
 * @execution server
 * @label Greeting
 * @buttonText Say Hello
 * @param {string} name Recipient.
 * @returns {Promise<string>} Greeting text.
 * @see JS_ADD
 */
async function greet(name) { return "Hello " + name; }
'''


def notebook(*sources):
    return {'metadata': {'kernelspec': {'name': 'deno', 'language': 'typescript'}},
            'cells': [{'cell_type': 'code', 'source': source} for source in sources]}


class Contents:
    def __init__(self, book):
        self.book = book

    def get(self, path, content=True):
        if not path:
            return {'type': 'directory', 'content': [{'type': 'notebook', 'path': 'nested/js.ipynb'}]}
        return {'type': 'notebook', 'path': path, 'content': self.book}


class DiscoveryTests(unittest.TestCase):
    def test_metadata_and_source(self):
        functions = scan_notebook(notebook(ADD, ACTION), 'nested/js.ipynb')
        a, b = functions
        self.assertEqual(a.parameters[1].default, '0')
        self.assertEqual(a.parameters[0].description, 'First number.')
        self.assertEqual(b.action['label'], 'Greeting')
        self.assertEqual(b.action['button_text'], 'Say Hello')
        self.assertEqual([e['id'] for e in functions_metadata(functions)['functions']], ['JS_ADD'])
        self.assertNotIn('greet(name)', functions_javascript(functions, 'https://api.example'))

    def test_invalid_exports_fail_with_cell_location(self):
        for source in [ADD.replace('@execution local', '@execution deno'),
                       ADD.replace('[b=0]', '[b=1]'), ADD.replace('a + b', 'a + missing'),
                       ADD.replace('{number} a', '{number} other'),
                       ADD.replace('function add', 'function* add')]:
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'nested/js.ipynb: Cell 1:'):
                scan_notebook(notebook(source), 'nested/js.ipynb')

    def test_python_unchanged_and_plain_javascript_ignored(self):
        self.assertEqual(scan_notebook(notebook('const value = 2;'), 'js.ipynb'), [])
        functions = scan_notebook({'cells': [{'cell_type': 'code', 'source': '@jupyter_function\ndef add(a,b): return a+b'}]}, 'py.ipynb')
        self.assertEqual(functions[0].language, 'python')

    def test_matrix_and_aliases(self):
        source = '''/** Matrix.
 * @jupyter_function MATRIX
 * @execution local
 * @param {number[][]} values Input.
 * @returns {number[][]} Result.
 */
function matrix(values) { return values.map(row => row.map(value => value * 2)); }
'''
        function = scan_notebook(notebook(source), 'matrix.ipynb')[0]
        self.assertEqual(function.result_dimensionality, 'matrix')
        self.assertEqual(function.form['inputs'][0]['type'], 'matrix')

    def test_generated_browser_calls(self):
        functions = scan_notebook(notebook(ADD, ACTION), 'nested/js.ipynb')
        from jupyterexcel.javascript import browser_exports
        script = browser_exports(functions, 'https://api.example') + '''
const assert = require('node:assert/strict');
(async () => {
  assert.equal(await JupyterExcelJavaScript.call('JS_ADD', [3,5]), 8);
  assert.equal(await JupyterExcelJavaScript.call('JS_ADD', [3]), 3);
  await assert.rejects(JupyterExcelJavaScript.call('JS_ADD', ['3',5]), /number/);
  globalThis.JupyterExcel = {call: async (url,args,post) => {
    assert.ok(url.includes('JS_GREET?version=')); assert.equal(post,true);
    return 'Hello ' + args[0];
  }};
  assert.equal(await JupyterExcelJavaScript.call('JS_GREET', ['Jim']), 'Hello Jim');
})().catch(error => {console.error(error); process.exitCode=1;});
'''
        run = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)


class AssetTests(unittest.IsolatedAsyncioTestCase):
    async def test_help_escapes_examples_and_rejects_broken_references(self):
        from jupyterexcel.jsdoc_help import generate_help
        functions = scan_notebook(notebook(ADD.replace('Adds two numbers.', '<script>alert(1)</script>'), ACTION), 'x.ipynb')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate_help(root, functions, 'Jupyter')
            page = (root / 'help/generated/JS_ADD.html').read_text()
            self.assertIn('&lt;script&gt;', page)
            self.assertNotIn('<script>', page)
            functions[1].documentation['related'] = ['MISSING']
            with self.assertRaisesRegex(ValueError, 'unresolved @see'):
                generate_help(root, functions, 'Jupyter')

    async def test_forms_help_and_python_exclusion(self):
        contents = Contents(notebook(ADD, ACTION))
        app = SimpleNamespace(contents_manager=contents, log=logging.getLogger('test'),
                              web_app=SimpleNamespace(settings={}), port=8888)
        with tempfile.TemporaryDirectory() as directory:
            store = AssetStore(app, output_dir=Path(directory), asset_url='https://assets.example')
            await store.generate()
            forms = json.loads((Path(directory) / 'actions.json').read_text())['actions']
            self.assertEqual([form['id'] for form in forms], ['JS_GREET'])
            metadata = json.loads((Path(directory) / 'functions.json').read_text())
            self.assertIn('JS_ADD', [entry['id'] for entry in metadata['functions']])
            script = (Path(directory) / 'functions.js').read_text()
            self.assertIn('CustomFunctions.associate("JS_ADD"', script)
            self.assertTrue((Path(directory) / 'help/generated/JS_ADD.html').is_file())
            page = (Path(directory) / 'help/generated/JS_GREET.html').read_text()
            self.assertIn('JS_ADD.html', page)
            self.assertIn('Say Hello', page)
            self.assertIn('server connection required', page)
            engine = SharedKernelExecutor(None, None, contents, 'test')
            self.assertEqual(await engine._notebooks(), [])
            self.assertFalse(await store.generate())


@unittest.skipUnless(shutil.which('deno'), 'Deno not installed')
class DenoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from jupyter_client import AsyncMultiKernelManager
        from jupyter_client.kernelspec import KernelSpecManager
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        spec = root / 'deno'
        spec.mkdir()
        (spec / 'kernel.json').write_text(json.dumps({'argv': [shutil.which('deno'), 'jupyter', '--kernel', '--conn', '{connection_file}'], 'display_name': 'Deno test', 'language': 'typescript'}))
        self.manager = AsyncMultiKernelManager(connection_dir=str(root), kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(root)]))
        self.contents = Contents(notebook(ADD, ACTION))
        self.executor = JavaScriptExecutor(self.manager, self.contents, timeout=20)

    async def asyncTearDown(self):
        await self.executor.stop()
        await self.manager.shutdown_all(now=True)
        self.temp.cleanup()

    async def test_real_deno_roundtrip_and_validation(self):
        result = await self.executor.execute('JS_GREET', ['Jim'])
        self.assertEqual(result, {'ok': True, 'result': 'Hello Jim'})
        self.assertEqual((await self.executor.execute('JS_GREET', ['Excel']))['result'], 'Hello Excel')
        with self.assertRaises(ExecutionError) as error:
            await self.executor.execute('JS_GREET', ['Jim'], version='old')
        self.assertEqual(error.exception.code, 'stale_export')
        with self.assertRaises(ExecutionError):
            await self.executor.execute('JS_GREET', [2])
        with self.assertRaises(ExecutionError):
            await self.executor.execute('JS_GREET', ['Jim'], action=False)
        self.contents.book = notebook(ADD, ACTION.replace('Hello ', 'Welcome '))
        self.assertEqual((await self.executor.execute('JS_GREET', ['Jim']))['result'], 'Welcome Jim')

    async def test_timeout_retires_kernel_and_errors_do_not_retry(self):
        self.contents.book = notebook(ACTION.replace('return "Hello " + name;', 'throw new Error("intentional");'))
        with self.assertRaisesRegex(ExecutionError, 'intentional'):
            await self.executor.execute('JS_GREET', ['Jim'])
        self.contents.book = notebook(ACTION.replace('return "Hello " + name;', 'await new Promise(resolve => setTimeout(resolve, 5000)); return name;'))
        self.executor.timeout = 1
        with self.assertRaises(ExecutionError) as error:
            await self.executor.execute('JS_GREET', ['Jim'])
        self.assertEqual(error.exception.code, 'timeout')
        self.assertEqual(self.executor.workers, {})
