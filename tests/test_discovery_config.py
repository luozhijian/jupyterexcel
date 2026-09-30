import json
import tempfile
import unittest
from types import SimpleNamespace
from jupyterexcel.discovery import selected_notebooks
from jupyterexcel.assets import AssetStore
from jupyterexcel.execution import SharedKernelExecutor


class DiscoveryConfigTests(unittest.IsolatedAsyncioTestCase):
    def manager(self, config=None, async_get=False):
        calls = []
        def directory(*children):
            return {'type': 'directory', 'content': [{'type': kind, 'path': path} for kind, path in children]}
        def notebook(name):
            return {'type': 'notebook', 'content': {'cells': [{'cell_type': 'code', 'source': '@jupyter_function\ndef ' + name + '(): return 1'}]}}
        models = {'': directory(('notebook', 'a.ipynb'), ('directory', 'nested'), ('directory', 'backup')),
                  'a.ipynb': notebook('root'), 'nested': directory(('notebook', 'nested/b.ipynb'), ('directory', 'nested/deep')),
                  'nested/b.ipynb': notebook('nested'), 'nested/deep': directory(('notebook', 'nested/deep/c.ipynb')),
                  'nested/deep/c.ipynb': notebook('deep'), 'backup': directory(('notebook', 'backup/d.ipynb')),
                  'backup/d.ipynb': notebook('backup')}
        if config is not None:
            models['']['content'].append({'type': 'file', 'path': 'jupyterexcel-config.json'})
            models['jupyterexcel-config.json'] = {'type': 'file', 'format': 'text', 'content': config if isinstance(config, str) else json.dumps(config)}
        def get(path, content=True):
            calls.append(path)
            return models[path]
        async def aget(path, content=True):
            return get(path, content)
        return SimpleNamespace(get=aget if async_get else get), calls

    async def test_absent_config_retains_recursion(self):
        for config in (None, {}, {'future': {}}):
            cm, calls = self.manager(config)
            self.assertEqual(len(await selected_notebooks(cm)), 4)

    async def test_root_only_prunes_and_matches_both_consumers(self):
        config = {'discovery': {'include': [{'folder': '.'}]}}
        cm, calls = self.manager(config, True)
        with tempfile.TemporaryDirectory() as output:
            store = AssetStore(SimpleNamespace(contents_manager=cm), output_dir=output)
            self.assertEqual([f.notebook for f in await store.discover()], ['a.ipynb'])
        executor = SharedKernelExecutor(None, None, cm, 'test')
        self.assertEqual([p for p, _ in await executor._notebooks()], ['a.ipynb'])
        self.assertNotIn('nested', calls)
        self.assertNotIn('backup', calls)

    async def test_selected_folders_recursion_overlap_and_empty(self):
        cm, calls = self.manager({'discovery': {'include': [{'folder': 'nested'}, {'folder': 'nested', 'recursive': True}, {'folder': 'nested/deep'}]}})
        self.assertEqual([p for p, _ in await selected_notebooks(cm)], ['nested/b.ipynb', 'nested/deep/c.ipynb'])
        self.assertEqual(calls.count('nested/b.ipynb'), 1)
        self.assertNotIn('a.ipynb', calls)
        self.assertNotIn('backup', calls)
        cm, _ = self.manager({'discovery': {'include': []}})
        self.assertEqual(await selected_notebooks(cm), [])

    async def test_invalid_configuration_fails_closed(self):
        invalid = ['{', [], {'discovery': []}, {'discovery': {'includes': []}}, {'discovery': {'include': 'all'}}]
        for folder in ('', '../outside', '/absolute', 'C:/absolute', 'nested\\deep', '**'):
            invalid.append({'discovery': {'include': [{'folder': folder}]}})
        invalid.append({'discovery': {'include': [{'folder': '.', 'recursive': 'false'}]}})
        for config in invalid:
            with self.subTest(config=config):
                cm, calls = self.manager(config)
                with self.assertRaisesRegex(ValueError, 'jupyterexcel-config.json'):
                    await selected_notebooks(cm)
                self.assertNotIn('a.ipynb', calls)

    async def test_missing_or_non_directory_include_fails(self):
        cm, _ = self.manager({'discovery': {'include': [{'folder': 'missing'}]}})
        with self.assertRaises(KeyError):
            await selected_notebooks(cm)
        cm, _ = self.manager({'discovery': {'include': [{'folder': 'a.ipynb'}]}})
        with self.assertRaisesRegex(ValueError, 'not a directory'):
            await selected_notebooks(cm)
