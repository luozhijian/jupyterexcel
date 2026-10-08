import json
from pathlib import Path
import unittest
from jupyterexcel.office_addin import scan_notebook, functions_metadata
from jupyterexcel.javascript import browser_exports


class GanttExports(unittest.TestCase):
    def test_notebook_export(self):
        notebook = json.loads(Path('JavaScriptExports.ipynb').read_text(encoding='utf-8'))
        functions = scan_notebook(notebook, 'JavaScriptExports.ipynb')
        gantt = next(f for f in functions if f.function_id == 'CREATE_GANTT')
        self.assertEqual(gantt.execution, 'local')
        self.assertEqual(gantt.kind, 'ribbon')
        self.assertTrue(gantt.action['output']['status_only'])
        self.assertEqual(gantt.action['output']['destinations'], ['taskpane'])
        self.assertNotIn('CREATE_GANTT', [f['id'] for f in functions_metadata(functions)['functions']])
        self.assertIn('async function createGantt', browser_exports(functions, 'https://localhost'))

    def test_office_only_allowed_for_ribbon(self):
        for tag, accepted in [('ribbonFunction', True), ('excelFunction', False)]:
            source = '/** Test.\n * @' + tag + ' TEST\n * @execution local\n * @returns {string} Status.\n */\nfunction f() { return Excel.run(() => "ok"); }'
            book = {'metadata': {'kernelspec': {'name': 'deno', 'language': 'javascript'}},
                    'cells': [{'cell_type': 'code', 'source': source}]}
            if accepted:
                self.assertEqual(len(scan_notebook(book, 'test.ipynb')), 1)
            else:
                with self.assertRaisesRegex(ValueError, 'Unsupported dependencies'):
                    scan_notebook(book, 'test.ipynb')
