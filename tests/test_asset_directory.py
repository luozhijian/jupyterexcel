import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jupyterexcel.assets import AssetStore


class AssetDirectoryTests(unittest.TestCase):
    def test_env_directory_used_directly_and_hub_user_appended(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'website'
            with patch.dict(os.environ, {'JUPYTEREXCEL_ASSET_DIR': str(destination)}):
                self.assertEqual(AssetStore(None).root, destination)
                self.assertEqual(AssetStore(None, username='alice').root, destination / 'alice')
                self.assertFalse(destination.exists())

    def test_unset_env_requires_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'should be defined'):
                AssetStore(None)

    def test_invalid_env_is_rejected_without_fallback(self):
        for value in ('', 'relative/path', 'https://example.com/assets'):
            with self.subTest(value=value), patch.dict(os.environ, {'JUPYTEREXCEL_ASSET_DIR': value}):
                with self.assertRaises(ValueError):
                    AssetStore(None)

    def test_file_cannot_be_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'file'
            file.write_text('existing')
            with patch.dict(os.environ, {'JUPYTEREXCEL_ASSET_DIR': str(file)}):
                with self.assertRaisesRegex(ValueError, 'not a directory'):
                    AssetStore(None)

    def test_explicit_test_destination_overrides_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'JUPYTEREXCEL_ASSET_DIR': 'invalid-relative-path'}):
                store = AssetStore(None, output_dir=directory)
                hub_store = AssetStore(None, username='alice', output_dir=directory)

                self.assertEqual(store.root, Path(directory))
                self.assertEqual(hub_store.root, Path(directory) / 'alice')
