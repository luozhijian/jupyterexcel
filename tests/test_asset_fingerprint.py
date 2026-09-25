import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET
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
        return AssetStore(
            self.app,
            output_dir=self.root/'output',
            template_dir=self.templates,
            asset_url='https://assets.example/excel-addin',
        )

    def manifest_namespace(self):
        tree = ET.parse(self.store.root / 'manifest.xml')
        return tree.find(
            ".//{http://schemas.microsoft.com/office/officeappbasictypes/1.0}String"
            "[@id='Functions.Namespace']"
        ).get('DefaultValue')

    async def test_namespace_defaults_for_unset_empty_and_whitespace(self):
        with patch.dict(os.environ):
            os.environ.pop('JUPYTEREXCEL_NAMESPACE', None)
            self.assertTrue(await self.store.generate())
            self.assertEqual(self.manifest_namespace(), 'Jupyter')
            for value in ('', '  \t\n'):
                os.environ['JUPYTEREXCEL_NAMESPACE'] = value
                self.assertFalse(await self.store.generate())
                self.assertEqual(self.manifest_namespace(), 'Jupyter')

    async def test_namespace_changes_publish_and_preserve_function_ids(self):
        with patch.dict(os.environ, {'JUPYTEREXCEL_NAMESPACE': 'Jupyter'}):
            await self.store.generate()
            previous = self.store.current
            metadata = (self.store.root / 'functions.json').read_bytes()
            with patch.dict(os.environ, {'JUPYTEREXCEL_NAMESPACE': '  MyCompany  '}):
                self.assertTrue(await self.store.generate())
                self.assertNotEqual(self.store.current, previous)
                self.assertEqual(self.manifest_namespace(), 'MyCompany')
                self.assertEqual((self.store.root / 'functions.json').read_bytes(), metadata)
                self.assertFalse(await self.store.generate())
            self.assertTrue(await self.store.generate())
            self.assertEqual(self.manifest_namespace(), 'Jupyter')

    async def test_invalid_namespace_preserves_published_assets(self):
        with patch.dict(os.environ, {'JUPYTEREXCEL_NAMESPACE': 'Jupyter'}):
            await self.store.generate()
            before = {str(p): p.read_bytes() for p in self.store.root.rglob('*') if p.is_file()}
            for value in ('1Bad', '_Bad', 'Bad Name', 'Bad-Name', 'A' * 33,
                          'Bad"/><x>', 'A&B', 'Bad\nName', 'München'):
                with self.subTest(value=value), patch.dict(os.environ, {'JUPYTEREXCEL_NAMESPACE': value}):
                    with self.assertRaisesRegex(ValueError, 'JUPYTEREXCEL_NAMESPACE must'):
                        await self.store.generate()
                    self.assertEqual(
                        {str(p): p.read_bytes() for p in self.store.root.rglob('*') if p.is_file()}, before)

    async def test_namespace_accepts_supported_characters_and_length_limits(self):
        for value in ('A', 'MyCompany_2.Tools', 'A' * 32):
            with self.subTest(value=value), patch.dict(os.environ, {'JUPYTEREXCEL_NAMESPACE': value}):
                self.assertTrue(await self.store.generate())
                self.assertEqual(self.manifest_namespace(), value)

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
        with patch.dict(os.environ, {"JUPYTEREXCEL_PUBLIC_URL": "https://changed.example:9999"}):
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



    async def test_license_notices_published_unchanged(self):
        await self.store.generate()
        project = Path(__file__).resolve().parents[1]
        for root_name, asset_name in (
            ('LICENSE', 'LICENSE.txt'),
            ('LICENSE-MIT', 'LICENSE-MIT.txt'),
            ('THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.txt'),
        ):
            expected = (project/root_name).read_bytes()
            self.assertEqual((self.templates/asset_name).read_bytes(), expected)
            self.assertEqual((self.store.root/asset_name).read_bytes(), expected)
        notice = 'taskpane.js.LICENSE.txt'
        self.assertEqual((self.store.root/notice).read_bytes(), (self.templates/notice).read_bytes())
        pointer = json.loads((self.store.root/'current.json').read_text())
        self.assertIn('LICENSE.txt', pointer['files'])
        self.assertFalse(await self.store.generate())


if __name__ == '__main__':
    unittest.main()
