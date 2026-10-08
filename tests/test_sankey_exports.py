import json
from pathlib import Path
import unittest
from jupyterexcel.office_addin import scan_notebook, functions_metadata
from jupyterexcel.javascript import browser_exports


class SankeyExports(unittest.TestCase):
    def test_selectors_and_bundle(self):
        book = json.loads(Path('JavaScriptExports.ipynb').read_text(encoding='utf-8'))
        exports = scan_notebook(book, 'JavaScriptExports.ipynb')
        item = next(f for f in exports if f.function_id == 'CREATE_SANKEY')
        self.assertEqual(item.execution, 'local')
        self.assertEqual([i['source'] for i in item.action['inputs']], ['range', 'cell'])
        self.assertTrue(all(i['reference_only'] for i in item.action['inputs']))
        self.assertTrue(item.action['output']['status_only'])
        self.assertNotIn('CREATE_SANKEY', [f['id'] for f in functions_metadata(exports)['functions']])
        self.assertIn('globalThis.JupyterExcelCharts', browser_exports(exports, 'https://localhost'))
