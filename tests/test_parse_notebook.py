"""Parse one notebook and generate Office files without executing any cells.

Run: python tests/test_parse_notebook.py NOTEBOOK_PATH OUTPUT_DIRECTORY
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

# Support direct execution without depending on the shell's current directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jupyterexcel.assets import AssetStore



#& "C:\Users\luozh\anaconda3\python.exe" `
#  "C:\Luo\Try1\jupyterexcel\tests\test_parse_notebook.py" `
#  "C:\Luo\Try1\jupyterexcel\TestingJupyter.ipynb" `
#  "C:\Luo\Try1\jupyterexcel\test-output\TestingJupyter"
async def generate_notebook(notebook_path, output_directory):
    source = Path(notebook_path).expanduser().resolve(strict=True)
    output = Path(output_directory).expanduser().resolve()
    if source.suffix.lower() != '.ipynb' or not source.is_file():
        raise ValueError('Input must be an existing .ipynb file.')
    protected = Path(__file__).resolve().parents[1] / 'DoNotChange'
    if output == protected or output.is_relative_to(protected):
        raise ValueError('The protected DoNotChange directory cannot be an output destination.')

    from jupyter_server.services.contents.filemanager import FileContentsManager
    from nbformat.sign import NotebookNotary
    manager = FileContentsManager(root_dir=source.anchor,
        notary=NotebookNotary(db_file=':memory:', secret=b'parse-only-test'))
    notebook_relative_path = source.relative_to(source.anchor).as_posix()

    class SingleNotebookContents:
        def get(self, path, content=True):
            if path == '':
                return {'type': 'directory', 'content': [
                    {'type': 'notebook', 'path': notebook_relative_path}
                ]}
            return manager.get(path, content=content)

    app = SimpleNamespace(
        contents_manager=SingleNotebookContents(),
        log=logging.getLogger('jupyterexcel.parse_test'),
        web_app=SimpleNamespace(settings={'base_url': '/'}),
        ip='localhost', port=8888,
    )
    store = AssetStore(app, data_dir=output)
    # The second argument is the exact destination, not a Jupyter data parent.
    store.root = output
    await store.generate()
    metadata = json.loads((output / 'functions.json').read_text(encoding='utf-8'))
    ET.parse(output / 'manifest.xml')
    script = output / f'functions.{store.current}.js'
    if not script.is_file():
        raise AssertionError('Versioned function script was not generated.')
    return {
        'notebook': str(source), 'output_directory': str(output),
        'version': store.current,
        'worksheet_functions': [item['id'] for item in metadata['functions']],
        'ribbon_functions': [item.excel_name for item in store.functions if item.kind == 'ribbon'],
        'manifest': str(output / 'manifest.xml'),
        'functions_json': str(output / 'functions.json'),
        'functions_js': str(script),
    }


class ParseNotebookTests(unittest.IsolatedAsyncioTestCase):
    async def test_generates_without_executing_cells(self):
        import nbformat
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'nested' / 'input.ipynb'
            source.parent.mkdir()
            notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(
                "raise RuntimeError('Cells must not execute')\n"
                "@jupyter_function(name='ADD')\ndef add(a,b): return a+b\n"
                "@ribbon_function('Report','A1')\ndef report(): return 1\n"
            )])
            nbformat.write(notebook, source)
            before = source.read_bytes()
            output = Path(directory) / 'output'
            result = await generate_notebook(source, output)
            self.assertEqual(result['worksheet_functions'], ['ADD'])
            self.assertEqual(result['ribbon_functions'], ['Report'])
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue((output / 'manifest.xml').exists())
            self.assertFalse((output / 'excel-addin').exists())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('notebook_path', type=Path)
    parser.add_argument('output_directory', type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(generate_notebook(args.notebook_path, args.output_directory))
    except Exception as error:
        parser.exit(1, f'Generation failed: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
