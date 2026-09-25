import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jupyterexcel.assets import AssetStore


class HelpPageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = '''@jupyter_function(name="string_join", description="Text <script>alert(1)</script>")
def join(a, b="hello"):
    raise RuntimeError("must not execute")
@jupyter_function(name="string.join")
def dotted(*values): return values
@ribbon_function("Ribbon")
def ribbon(): pass
'''
        contents = SimpleNamespace(get=self.get)
        self.app = SimpleNamespace(contents_manager=contents, log=logging.getLogger('test'),
                                   web_app=SimpleNamespace(settings={'base_url': '/'}), port=8888)
        self.templates = self.root / 'templates'
        shutil.copytree(Path(__import__('jupyterexcel').__file__).parent / 'addin_template', self.templates)
        self.store = self.make_store()
        self.env = patch.dict(os.environ, {'JUPYTEREXCEL_NAMESPACE': 'MyNamespace'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def get(self, path, content=True):
        if not path:
            return {'type': 'directory', 'content': [{'type': 'notebook', 'path': 'nested/book.ipynb'}]}
        return {'type': 'notebook', 'path': path, 'content': {'cells': [{'cell_type': 'code', 'source': self.source}]}}

    def make_store(self, username=None):
        return AssetStore(self.app, output_dir=self.root / 'output', template_dir=self.templates,
                          asset_url='https://assets.example/excel-addin/', username=username)

    async def test_metadata_pages_and_safe_content(self):
        await self.store.generate()
        metadata = json.loads((self.store.root / 'functions.json').read_text())['functions']
        for entry in metadata:
            self.assertEqual(entry['helpUrl'], 'https://assets.example/excel-addin/help/functions/' + entry['id'] + '.html')
            self.assertTrue((self.store.root / 'help/functions' / (entry['id'] + '.html')).is_file())
        page = (self.store.root / 'help/functions/string_join.html').read_text(encoding='utf-8')
        self.assertIn('=MyNamespace.string_join(a, [b])', page)
        self.assertIn('Python default:', page)
        self.assertIn('hello', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>', page)
        self.assertIn('Repeating argument', (self.store.root / 'help/functions/string.join.html').read_text())
        self.assertFalse((self.store.root / 'help/functions/Ribbon.html').exists())
        state = json.loads((self.store.root / 'current.json').read_text())
        self.assertFalse(any(name.startswith('help/') for name in state['files']))
        self.assertFalse((self.store.root / 'help_template.html').exists())

    async def test_preserve_edits_repair_missing_and_keep_removed_pages(self):
        await self.store.generate()
        page = self.store.root / 'help/functions/string_join.html'
        page.write_bytes(b'Manually maintained documentation')
        stamp = page.stat().st_mtime_ns
        self.assertFalse(await self.store.generate())
        self.assertEqual(page.read_bytes(), b'Manually maintained documentation')
        self.assertEqual(page.stat().st_mtime_ns, stamp)
        (self.templates / 'help_template.html').write_text('<h1>{{FUNCTION_NAME}}</h1>New template', encoding='utf-8')
        restarted = self.make_store()
        self.assertFalse(await restarted.generate())
        self.assertEqual(page.stat().st_mtime_ns, stamp)
        page.unlink()
        self.assertFalse(await restarted.generate())
        self.assertIn('New template', page.read_text())
        self.source = self.source.replace('string_join', 'Renamed')
        await restarted.generate()
        self.assertTrue(page.exists())
        self.assertTrue((self.store.root / 'help/functions/Renamed.html').exists())

    async def test_hub_user_paths_and_builtin_display_name(self):
        store = self.make_store('a.b@example.com')
        await store.generate()
        metadata = json.loads((store.root / 'functions.json').read_text())['functions']
        builtin = next(e for e in metadata if e['id'] == 'MANIFESTURL')
        self.assertEqual(builtin['helpUrl'], 'https://assets.example/excel-addin/' + store.username_path + '/help/functions/MANIFESTURL.html')
        page = (store.root / 'help/functions/MANIFESTURL.html').read_text()
        self.assertIn('=MyNamespace.' + builtin['name'] + '()', page)
        self.assertIn('takes no arguments', page)


if __name__ == '__main__':
    unittest.main()
