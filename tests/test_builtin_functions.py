import json
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from jupyterexcel.assets import AssetStore
from jupyterexcel.office_addin import scan_notebook


class BuiltinTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_notebooks_hub_urls_version_and_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(contents_manager=SimpleNamespace(get=AsyncMock(
                return_value={'type': 'directory', 'content': []})), log=logging.getLogger('test'),
                web_app=SimpleNamespace(settings={'base_url': '/user/alice/'}), port=8888)
            store = AssetStore(app, output_dir=directory, asset_url='https://example.com/addin', username='alice')
            self.assertTrue(await store.generate())
            metadata = json.loads(store.resolve('functions.json').read_text())
            self.assertEqual({f['id'] for f in metadata['functions']},
                             {'MANIFESTURL', 'SERVERURL', 'ADDINVERSION', 'ASSETVERSION'})
            for name in ('functions.js', 'jupyter-config.js'):
                script = store.resolve(name).read_text()
                self.assertIn('https://example.com/addin/alice/manifest.xml', script)
                self.assertIn('"assetVersion": "' + store.current + '"', script)
                self.assertNotIn('__JUPYTEREXCEL_BATCH_VERSION__', script)
            version = store.current
            self.assertFalse(await store.generate())
            self.assertEqual(store.current, version)
            notebook = {'cells': [{'cell_type':'code', 'source':
                '@jupyter_function(name="manifesturl")\ndef f(): return 1'}]}
            store.discover = AsyncMock(return_value=scan_notebook(notebook, 'nested/a.ipynb'))
            with self.assertRaisesRegex(ValueError, 'reserved.*MANIFESTURL'):
                await store.generate()
            self.assertEqual(store.current, version)
