import json
import logging
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jupyterexcel.assets import AssetStore


class NotebookContents:
    source = '@jupyter_function(name="ADD")\ndef add(a,b): return a+b'

    def get(self, path, content=True):
        if not path:
            return {'type':'directory', 'content':[{'type':'notebook','path':'nested/book.ipynb'}]}
        return {'type':'notebook','path':path,'content':{'cells':[
            {'cell_type':'code','source':self.source}]}}


class FingerprintTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contents = NotebookContents()
        self.app = SimpleNamespace(contents_manager=self.contents, log=logging.getLogger('test'),
                                   web_app=SimpleNamespace(settings={'base_url':'/'}), port=8888)
        self.templates = self.root/'templates'
        shutil.copytree(Path(__import__('jupyterexcel').__file__).parent/'addin_template', self.templates)
        self.store = self.make_store()

    def make_store(self):
        return AssetStore(self.app, output_dir=self.root/'output', template_dir=self.templates)

    async def test_unchanged_after_restart_keeps_every_file_timestamp(self):
        self.assertTrue(await self.store.generate())
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.store.root.rglob('*') if p.is_file()}
        restarted = self.make_store()
        self.assertFalse(await restarted.generate())
        self.assertEqual(restarted.current, self.store.current)
        after = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.store.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    async def test_body_edit_does_not_change_assets_but_metadata_does(self):
        await self.store.generate()
        self.contents.source = self.contents.source.replace('return a+b', 'return a-b')
        self.assertFalse(await self.store.generate())
        previous = self.store.current
        self.contents.source = self.contents.source.replace('name="ADD"', 'name="SUBTRACT"')
        self.assertTrue(await self.store.generate())
        self.assertNotEqual(previous, self.store.current)

    async def test_template_icon_and_api_changes_trigger_generation(self):
        await self.store.generate()
        for name in ('jupyter-runtime.js', 'assets/icon-32.png'):
            file = self.templates/name
            file.write_bytes(file.read_bytes() + b'\n')
            self.assertTrue(await self.store.generate())
        self.app.port = 9999
        self.assertTrue(await self.store.generate())

    async def test_missing_or_modified_public_files_are_repaired_without_version(self):
        await self.store.generate()
        previous = self.store.current
        manifest = self.store.root/'manifest.xml'
        metadata = self.store.root/'functions.json'
        expected = metadata.read_bytes()
        manifest.unlink()
        metadata.write_text('damaged')
        self.assertFalse(await self.store.generate())
        self.assertEqual(previous, self.store.current)
        self.assertTrue(manifest.is_file())
        self.assertEqual(metadata.read_bytes(), expected)

    async def test_missing_archive_or_legacy_pointer_rebuilds(self):
        await self.store.generate()
        previous = self.store.current
        (self.store.root/'versions'/previous/'functions.json').unlink()
        self.assertTrue(await self.store.generate())
        previous = self.store.current
        (self.store.root/'current.json').write_text(json.dumps({'version':previous}))
        self.assertTrue(await self.store.generate())

    async def test_failed_publication_keeps_success_pointer(self):
        await self.store.generate()
        pointer = self.store.root/'current.json'
        previous = pointer.read_bytes()
        self.contents.source = self.contents.source.replace('name="ADD"', 'name="NEW"')
        with patch.object(self.store, '_publish_files', side_effect=PermissionError('test')):
            with self.assertRaises(PermissionError):
                await self.store.generate()
        self.assertEqual(pointer.read_bytes(), previous)
        self.assertTrue(await self.store.generate())


if __name__ == '__main__':
    unittest.main()
