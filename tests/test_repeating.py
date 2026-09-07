import json
import shutil
import subprocess
import unittest
from jupyterexcel import jupyter_function
from jupyterexcel.office_addin import scan_notebook, functions_metadata, functions_javascript

class RepeatingTests(unittest.TestCase):
    def test_runtime_static_and_bridge(self):
        for prefix in ('', 'factor, '):
            source = '@jupyter_function(parameter_types={"values":"number"}, parameter_dimensionality={"values":"matrix"})\ndef product(' + prefix + '*values): return values'
            ns = {'jupyter_function': jupyter_function}
            exec(source, ns)
            self.assertTrue(ns['product'].__jupyterexcel_function__['parameters'][-1]['repeating'])
            functions = scan_notebook({'cells':[{'cell_type':'code','source':source}]}, 'nested/test.ipynb')
            parameter = functions_metadata(functions)['functions'][0]['parameters'][-1]
            self.assertTrue(parameter['repeating'])
            self.assertEqual(parameter['dimensionality'], 'matrix')
            if not shutil.which('node'):
                self.skipTest('Node required for generated bridge test')
            script = functions_javascript(functions, 'http://localhost:8888')
            registration = script[script.rindex('CustomFunctions.associate'):]
            values = [[[2]], [[3,4],[5,6]]]
            args = [10, values] if prefix else [values]
            args.append({'invocationId': 8, '_functionName': 'PRODUCT'})
            expected = [10] + values if prefix else values
            harness = 'let fn; const CustomFunctions={associate:(id,f)=>fn=f}; const jupyterExcelCall=(url,args)=>args;'
            harness += registration + '\nconsole.log(JSON.stringify(fn(...' + json.dumps(args) + ')));'
            actual = subprocess.check_output(['node','-e',harness], text=True)
            self.assertEqual(json.loads(actual), expected)

    def test_repeating_defaults_and_invalid_keyword_tail(self):
        for source in ('@jupyter_function\ndef f(*values): return values',):
            functions = scan_notebook({'cells':[{'cell_type':'code','source':source}]}, 'test.ipynb')
            p = functions_metadata(functions)['functions'][0]['parameters'][0]
            self.assertEqual(p['type'], 'any')
            self.assertEqual(p['dimensionality'], 'scalar')
            self.assertTrue(p['repeating'])
        source = '@jupyter_function\ndef f(*values, mode=1): return values'
        with self.assertRaises(ValueError):
            scan_notebook({'cells':[{'cell_type':'code','source':source}]}, 'test.ipynb')
        with self.assertRaises(ValueError):
            exec(source, {'jupyter_function':jupyter_function})

    def test_fixed_parameters_exclude_invocation(self):
        if not shutil.which('node'):
            self.skipTest('Node required for generated bridge test')
        for signature, values in [('a,b,c', [1,2,3]), ('', []), ('value', [{'invocationId': 99}])]:
            source = '@jupyter_function\ndef f(' + signature + '): return None'
            functions = scan_notebook({'cells':[{'cell_type':'code','source':source}]}, 'test.ipynb')
            script = functions_javascript(functions, 'https://localhost:8888')
            registration = script[script.rindex('CustomFunctions.associate'):]
            args = values + [{'invocationId': 8, '_functionName': 'F'}]
            harness = 'let fn; const CustomFunctions={associate:(id,f)=>fn=f}; const jupyterExcelCall=(url,args)=>args;'
            harness += registration + '\nconsole.log(JSON.stringify(fn(...' + json.dumps(args) + ')));'
            self.assertEqual(json.loads(subprocess.check_output(['node','-e',harness], text=True)), values)
