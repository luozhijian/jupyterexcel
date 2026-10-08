import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import venv
from types import SimpleNamespace
from jupyterexcel import execution_profile, jupyter_function, ribbon_function
from jupyterexcel.office_addin import scan_notebook
from jupyterexcel.profiles import validate_profiles, resolve_profile, notebook_language, ProfileWarnings
from jupyterexcel.profile_executor import ProfileExecutor
from jupyterexcel.profile_pool import KernelBudget
from jupyterexcel.execution import ExecutionError


def notebook(source, language='python', kernel='python3', profile=None):
    return {'metadata': {'kernelspec': {'name': kernel, 'language': language},
                          'jupyterexcel': {'execution_profile': profile} if profile else {}},
            'cells': [{'cell_type': 'code', 'source': source}]}


class Contents:
    def __init__(self, books):
        self.books = books

    def get(self, path, content=True):
        if not path:
            return {'type': 'directory', 'content': [{'type': 'notebook', 'path': key} for key in self.books]}
        return {'type': 'notebook', 'path': path, 'content': self.books[path]}


class MetadataTests(unittest.TestCase):
    def test_fallback_warning_scope_and_routing_changes(self):
        from unittest.mock import Mock
        profiles, defaults, _ = validate_profiles({})
        function = SimpleNamespace(execution_profile=None, notebook='a.ipynb')
        book = notebook('', kernel='conda-base-py')
        logger = Mock()
        warnings = ProfileWarnings(logger)
        self.assertEqual(resolve_profile(function, book, profiles, defaults), 'python-default')
        logger.warning.assert_not_called()
        for _ in range(3):
            warnings.resolve(function, book, profiles, defaults)
        self.assertEqual(logger.warning.call_count, 1)
        profiles['python-default']['kernel_name'] = 'other-python'
        warnings.resolve(function, book, profiles, defaults)
        self.assertEqual(logger.warning.call_count, 2)
        function.notebook = 'nested/a.ipynb'
        warnings.resolve(function, book, profiles, defaults)
        self.assertEqual(logger.warning.call_count, 3)
        ProfileWarnings(logger).resolve(function, book, profiles, defaults)
        self.assertEqual(logger.warning.call_count, 4)
        function.execution_profile = 'missing'
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            warnings.resolve(function, book, profiles, defaults)
        self.assertEqual(logger.warning.call_count, 4)

    def test_unmapped_kernel_warns_and_uses_language_default(self):
        profiles, defaults, _ = validate_profiles({})
        for language, kernel, expected in [('python', 'conda-base-py', 'python-default'),
                                            ('javascript', 'custom-deno', 'javascript')]:
            book = notebook('', language=language, kernel=kernel)
            function = SimpleNamespace(execution_profile=None, notebook='sample.ipynb')
            warnings = ProfileWarnings()
            with self.assertLogs('jupyterexcel.profiles', level='WARNING') as logs:
                self.assertEqual(warnings.resolve(function, book, profiles, defaults), expected)
                self.assertEqual(warnings.resolve(function, book, profiles, defaults), expected)
            self.assertEqual(len(logs.output), 1)
            self.assertIn(kernel, logs.output[0])
            self.assertIn(expected, logs.output[0])
            self.assertIn('sample.ipynb', logs.output[0])
            function.execution_profile = 'missing'
            with self.assertRaisesRegex(ValueError, 'Unknown'):
                resolve_profile(function, book, profiles, defaults)

    def test_decorator_orders_and_normal_calls(self):
        for decorators in ('@execution_profile("finance")\n@jupyter_function',
                           '@jupyter_function\n@execution_profile("finance")'):
            source = decorators + '\ndef add(a,b): return a+b'
            scope = dict(execution_profile=execution_profile, jupyter_function=jupyter_function)
            exec(source, scope)
            self.assertEqual(scope['add'](2, 3), 5)
            self.assertEqual(scope['add'].__jupyterexcel_execution_profile__, 'finance')
            self.assertEqual(scan_notebook(notebook(source), 'a.ipynb')[0].execution_profile, 'finance')
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            execution_profile('other')(scope['add'])

    def test_ribbon_profile(self):
        source = '@execution_profile("finance")\n@ribbon_function("ACTION", inputs={})\ndef action(): return {"result": [[1]]}'
        scope = dict(execution_profile=execution_profile, ribbon_function=ribbon_function)
        exec(source, scope)
        self.assertEqual(scan_notebook(notebook(source), 'a.ipynb')[0].execution_profile, 'finance')
        self.assertEqual(scope['action']()['result'], [[1]])

    def test_resolution_and_metadata_validation(self):
        profiles, defaults, _ = validate_profiles({'profiles': {'finance': {'language': 'python', 'kernel_name': 'finance-venv'}}})
        book = notebook('@jupyter_function\ndef f(): return 1', kernel='finance-venv')
        function = scan_notebook(book, 'a.ipynb')[0]
        self.assertEqual(resolve_profile(function, book, profiles, defaults), 'finance')
        function.execution_profile = 'javascript'
        with self.assertRaisesRegex(ValueError, 'does not match'):
            resolve_profile(function, book, profiles, defaults)
        function.execution_profile = 'missing'
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            resolve_profile(function, book, profiles, defaults)
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            notebook_language(notebook('', language='javascript', kernel='python3'))
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            notebook_language(notebook('', language='unknown', kernel='other'))

    def test_jsdoc_profile_and_notebook_default(self):
        source = '''/** Example.
 * @excelFunction TEST
 * @execution server
 * @executionProfile js-test
 * @returns {number} Value.
 */
function test() { return 1; }
'''
        book = notebook(source, language='typescript', kernel='deno')
        self.assertEqual(scan_notebook(book, 'js.ipynb')[0].execution_profile, 'js-test')
        with self.assertRaisesRegex(ValueError, 'local exports'):
            scan_notebook(notebook(source.replace('@execution server', '@execution local'), language='typescript', kernel='deno'), 'js.ipynb')

    def test_configuration_limits_disabled_r_and_budget(self):
        profiles, _, _ = validate_profiles({'profiles': {'r': {'language': 'r', 'kernel_name': 'ir', 'enabled': False}}})
        self.assertFalse(profiles['r']['enabled'])
        for config in ({'total_max_kernels': 0}, {'profiles': {'r': {'language': 'r', 'kernel_name': 'ir'}}},
                       {'profiles': {'bad': {'language': 'python', 'kernel_name': 'x', 'max_kernels': 0}}}):
            with self.assertRaises(ValueError):
                validate_profiles(config)
        budget = KernelBudget(1)
        self.assertTrue(budget.reserve())
        self.assertFalse(budget.reserve())
        budget.release()
        self.assertTrue(budget.reserve())

    def test_notebook_defaults_and_conflicts(self):
        source = '@jupyter_function\ndef f(): return 1'
        book = notebook(source, profile='finance')
        self.assertEqual(scan_notebook(book, 'a.ipynb')[0].execution_profile, 'finance')
        conflicting = '@execution_profile("a")\n@execution_profile("b")\n' + source
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            scan_notebook(notebook(conflicting), 'a.ipynb')
        from jupyterexcel.config import validate
        config = validate({'server': {'public_url': 'https://api.example'},
                           'assets': {'directory': '/tmp/assets', 'url': 'https://assets.example'},
                           'execution': {'min_kernels': 0, 'profiles': {'finance': {'language': 'python', 'kernel_name': 'finance'}}}}, Path('config.json').resolve())
        self.assertEqual(config['execution']['profiles']['finance']['kernel_name'], 'finance')


class RealProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from jupyter_client import AsyncMultiKernelManager
        from jupyter_client.kernelspec import KernelSpecManager
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.venvs = {}
        for name in ('env-a', 'env-b'):
            directory = self.root / name
            venv.EnvBuilder(system_site_packages=True, with_pip=False).create(directory)
            interpreter = directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            self.venvs[name] = interpreter
            spec = self.root / 'specs' / name
            spec.mkdir(parents=True)
            (spec / 'kernel.json').write_text(json.dumps({'argv': [str(interpreter), '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
                'display_name': 'Same friendly name', 'language': 'python',
                'env': {'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'IPYTHONDIR': str(self.root / 'ipython')}}))
        if shutil.which('deno'):
            spec = self.root / 'specs' / 'deno'
            spec.mkdir()
            (spec / 'kernel.json').write_text(json.dumps({'argv': [shutil.which('deno'), 'jupyter', '--kernel', '--conn', '{connection_file}'], 'display_name': 'Deno', 'language': 'typescript'}))
        self.manager = AsyncMultiKernelManager(connection_dir=str(self.root), kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(self.root / 'specs')]))
        source = 'from jupyterexcel import execution_profile, jupyter_function\nimport sys, time\n@jupyter_function(name="{id}")\n@execution_profile("{profile}")\ndef identity(delay=0):\n time.sleep(delay)\n return sys.executable'
        self.contents = Contents({'a.ipynb': notebook(source.format(id='A', profile='finance'), kernel='env-a'),
                                  'b.ipynb': notebook(source.format(id='B', profile='science'), kernel='env-b')})
        settings = {'min_kernels': 0, 'queue_scale_up_after_seconds': .01, 'scale_up_cooldown_seconds': .01,
                    'profiles': {'finance': {'language': 'python', 'kernel_name': 'env-a', 'min_kernels': 0, 'max_kernels': 2},
                                 'science': {'language': 'python', 'kernel_name': 'env-b', 'min_kernels': 0, 'max_kernels': 1}},
                    'total_max_kernels': 4}
        self.executor = ProfileExecutor(self.manager, None, self.contents, 'test', settings)

    async def asyncTearDown(self):
        await self.executor.stop()
        await self.manager.shutdown_all(now=True)
        self.temp.cleanup()

    async def test_real_venv_routing_and_concurrency(self):
        a, b = await asyncio.gather(self.executor.execute('A', []), self.executor.execute('B', []))
        self.assertEqual(Path(a['result']), self.venvs['env-a'])
        self.assertEqual(Path(b['result']), self.venvs['env-b'])
        results = await asyncio.gather(self.executor.execute('A', [2]), self.executor.execute('A', [2]))
        self.assertTrue(all(r['ok'] for r in results))
        self.assertEqual(len(self.executor.pools['finance'].workers), 2)
        self.assertLessEqual(self.executor.budget.used, 4)
        self.assertTrue(any(k['profile'] == 'finance' for k in self.executor.status()['kernels']))

    async def test_missing_kernel_never_falls_back(self):
        self.executor.pools['finance'].settings['kernel_name'] = 'missing'
        with self.assertRaisesRegex(ExecutionError, 'finance'):
            await self.executor.execute('A', [])
        self.assertEqual(self.executor.budget.used, 0)

    async def test_idle_retirement_and_minimum_zero(self):
        pool = self.executor.pools['science']
        pool.settings['idle_shutdown_seconds'] = .1
        await pool.start()
        await asyncio.sleep(.15)
        self.assertEqual(pool.workers, [])
        await self.executor.execute('B', [])
        async with asyncio.timeout(5):
            while pool.workers:
                await asyncio.sleep(.05)
        self.assertEqual(self.executor.budget.used, 0)

    async def test_notebooks_do_not_share_globals_and_global_cap(self):
        self.executor.budget.limit = 1
        await self.executor.execute('A', [])
        original = self.executor.pools['finance'].workers[0].id
        await self.executor.execute('B', [])
        self.assertEqual(self.executor.budget.used, 1)
        self.assertFalse(self.executor.pools['finance'].workers)
        self.assertNotEqual(original, self.executor.pools['science'].workers[0].id)
        source = 'from jupyterexcel import execution_profile,jupyter_function\n@jupyter_function(name="C")\n@execution_profile("science")\ndef check(): return "identity" in globals()'
        self.contents.books['c.ipynb'] = notebook(source, kernel='env-b')
        self.assertFalse((await self.executor.execute('C', []))['result'])

    async def test_js_profile_and_isolation(self):
        if not shutil.which('deno'):
            self.skipTest('Deno not installed')
        source = '''/** Test.
 * @excelFunction JS
 * @execution server
 * @executionProfile javascript
 * @returns {number} Result.
 */
function value() { return 7; }
'''
        self.contents.books['js.ipynb'] = notebook(source, language='typescript', kernel='deno')
        self.assertEqual((await self.executor.execute('JS', []))['result'], 7)
        self.contents.books['js.ipynb']['cells'][0]['source'] = source.replace('return 7', 'return 8')
        self.assertEqual((await self.executor.execute('JS', []))['result'], 8)
        self.assertEqual(len(self.executor.pools['javascript'].workers), 1)
