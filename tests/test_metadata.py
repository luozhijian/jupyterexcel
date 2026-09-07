import unittest
from unittest.mock import patch

from jupyterexcel import jupyter_function
from jupyterexcel.office_addin import scan_notebook, functions_metadata
from jupyterexcel import utils


class MetadataTests(unittest.TestCase):
    def metadata(self, source):
        notebook = {'cells': [{'cell_type': 'code', 'source': source}]}
        return functions_metadata(scan_notebook(notebook, 'nested/example.ipynb'))['functions'][0]

    def test_missing_values_default_to_any_scalar(self):
        with patch.dict(utils.jupyterexcel_functions, clear=True):
            @jupyter_function
            def default(a, b=1):
                return a
            runtime = default.__jupyterexcel_function__
            self.assertEqual(runtime['result_type'], 'any')
            self.assertEqual(runtime['result_dimensionality'], 'scalar')
            self.assertTrue(all(p['type'] == 'any' and p['dimensionality'] == 'scalar' for p in runtime['parameters']))
        metadata = self.metadata('@jupyter_function\ndef default(a,b=1): return a')
        self.assertEqual(metadata['result'], {'type':'any','dimensionality':'scalar'})
        self.assertEqual(metadata['parameters'][0]['dimensionality'], 'scalar')
        self.assertTrue(metadata['parameters'][1]['optional'])

    def test_matrix_input_result_and_partial_overrides(self):
        source = '''@jupyter_function(name="SCALE", parameter_types={"values":"number"},
            parameter_dimensionality={"values":"matrix"},
            result_type="number", result_dimensionality="matrix")
def scale(values, factor=2):
    return [[v * factor for v in row] for row in values]
'''
        namespace = {'jupyter_function': jupyter_function}
        with patch.dict(utils.jupyterexcel_functions, clear=True):
            exec(source, namespace)
            function = namespace['scale']
            runtime = function.__jupyterexcel_function__
            self.assertEqual(function([[1,2],[3,4]]), [[2,4],[6,8]])
            metadata = self.metadata(source)
            self.assertEqual(metadata['result'], {'type':'number','dimensionality':'matrix'})
            for actual, expected in zip(metadata['parameters'], runtime['parameters']):
                self.assertEqual(actual['type'], expected['type'])
                self.assertEqual(actual['dimensionality'], expected['dimensionality'])
            self.assertEqual(metadata['parameters'][1]['type'], 'any')
            self.assertEqual(metadata['parameters'][1]['dimensionality'], 'scalar')

    def test_invalid_metadata_rejected_by_decorator_and_scanner(self):
        for options in (
            {'result_dimensionality':'vector'},
            {'parameter_dimensionality':{'a':'2d'}},
            {'parameter_types':{'a':'float'}},
            {'parameter_dimensionality':{'missing':'matrix'}},
            {'parameter_types':['number']},
        ):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    jupyter_function(**options)(lambda a: a)
                keywords = ', '.join(f'{k}={v!r}' for k,v in options.items())
                with self.assertRaises(ValueError):
                    self.metadata(f'@jupyter_function({keywords})\ndef f(a): return a')

    def test_nonliteral_metadata_is_not_silently_defaulted(self):
        with self.assertRaisesRegex(ValueError, 'must be a literal'):
            self.metadata('@jupyter_function(result_dimensionality=MODE)\ndef f(): return 1')


if __name__ == '__main__':
    unittest.main()
