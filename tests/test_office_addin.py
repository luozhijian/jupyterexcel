import json
import logging
from types import SimpleNamespace
from jupyterexcel.assets import AssetStore
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from jupyterexcel.office_addin import discover_notebooks, functions_javascript, functions_metadata, scan_notebook


NOTEBOOK = {"cells": [
    {"cell_type": "code", "source": [
        "@jupyter_function(name='ADD', description='Add values', parameter_types={'a': 'number', 'b': 'number'}, result_type='number')\n",
        "def add(a, b=2):\n", "    return a + b\n",
    ]},
    {"cell_type": "code", "source": "@ribbon_function('Run report', 'A1')\ndef report():\n    return 1\n"},
]}


class FakeContentsManager:
    def get(self, path, content=True):
        if path == "":
            return {"type": "directory", "content": [{"type": "notebook", "path": "folder/book.ipynb"}]}
        return {"type": "notebook", "path": path, "content": NOTEBOOK}


class OfficeAddinTests(unittest.TestCase):
    def test_scans_both_decorators_separately(self):
        functions = scan_notebook(NOTEBOOK, "folder/book.ipynb")
        self.assertEqual([item.kind for item in functions], ["jupyter", "ribbon"])
        self.assertEqual(functions[0].function_id, "ADD")
        self.assertTrue(functions[0].parameters[1].optional)

    def test_discovers_nested_notebook_and_generates_metadata(self):
        functions = discover_notebooks(FakeContentsManager())
        metadata = functions_metadata(functions)
        self.assertEqual(len(metadata["functions"]), 1)
        self.assertEqual(metadata["functions"][0]["parameters"][0]["type"], "number")
        json.dumps(metadata)

    def test_javascript_calls_exported_id_and_associates_id(self):
        script = functions_javascript(discover_notebooks(FakeContentsManager()), "https://localhost:3000")
        self.assertIn("/Excel/ADD", script)
        self.assertIn('CustomFunctions.associate("ADD"', script)
        self.assertIn("Authorization: 'token ' + auth.token", script)
        self.assertIn("if (!present) throw new Error(MISSING_TOKEN_MESSAGE)", script)
        self.assertIn("body: JSON.stringify(args)", script)

    def test_custom_runtime_is_bundled_before_registrations(self):
        with tempfile.TemporaryDirectory() as directory:
            templates = Path(directory)
            (templates / 'jupyter-runtime.js').write_text('async function jupyterExcelCall() { return 42; }')
            (templates / 'functions.js').write_text('{{FUNCTIONS_RUNTIME}}\n{{FUNCTION_REGISTRATIONS}}')
            script = functions_javascript(discover_notebooks(FakeContentsManager()), 'https://api.example.com', templates)
            self.assertIn('return 42;', script)
            self.assertLess(script.index('async function'), script.index('CustomFunctions.associate'))
            self.assertNotIn('{{FUNCTIONS_', script)
            self.assertNotIn('Report', script)
            (templates / 'functions.js').write_text('{{FUNCTIONS_REGISTRATIONS}}')
            with self.assertRaises(ValueError):
                functions_javascript([], 'https://api.example.com', templates)

    def test_manifest_template_is_rendered_with_asset_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            app = SimpleNamespace(
                web_app=SimpleNamespace(settings={'base_url': '/'}),
                port=8888, log=logging.getLogger('test'))
            store = AssetStore(app, output_dir=output, asset_url='https://assets.example/addin')
            store._render(output, [])
            manifest = (output / 'manifest.xml').read_text(encoding='utf-8')
            tree = ET.fromstring(manifest)
            ns = {'bt': 'http://schemas.microsoft.com/office/officeappbasictypes/1.0'}
            urls = {e.get('id'): e.get('DefaultValue') for e in tree.findall('.//bt:Url', ns)}
            self.assertEqual(urls['Functions.Script.Url'], 'https://assets.example/addin/functions.js')
            self.assertEqual(urls['Functions.Metadata.Url'], 'https://assets.example/addin/functions.json')
            self.assertNotIn('{{ASSET_BASE_URL}}', manifest)
            template = ET.parse(store.templates / 'manifest.xml')
            self.assertEqual(
                tree.find(".//bt:String[@id='Functions.Namespace']", ns).attrib,
                template.find(".//bt:String[@id='Functions.Namespace']", ns).attrib)


if __name__ == "__main__":
    unittest.main()
