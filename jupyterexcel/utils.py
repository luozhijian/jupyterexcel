

# -*- coding: utf-8 -*-
"""
Created on Mon Jul  1 22:18:04 2019
reference http://scottlobdell.me/2015/04/decorators-arguments-python/
@author: Administrator
"""
import inspect
from .metadata import validate_metadata


#a dictionary to save all cacll back functions

jupyterexcel_ribbon_functions={}
jupyterexcel_functions = {}


def jupyter_function(_function=None, *, name=None, description=None,
                     result_type="any", parameter_types=None,
                     result_dimensionality="scalar", parameter_dimensionality=None):
    """Mark a notebook function as an Excel custom function.

    The decorator works both as ``@jupyter_function`` and as
    ``@jupyter_function(name="ADD", description="Add two values")``.
    Metadata is attached to the function as well as registered in the current
    kernel.  The server's notebook scanner reads the decorator from source, so
    notebooks do not need to be executed merely to build the Office manifest.
    """
    def decorate(function):
        function_name = function.__name__
        signature = inspect.signature(function)
        validate_metadata(signature.parameters, parameter_types, parameter_dimensionality,
                          result_type, result_dimensionality)
        parameters = list(signature.parameters.values())
        if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in parameters) and any(
                p.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_KEYWORD) for p in parameters):
            raise ValueError('Repeating worksheet parameters must be last; keyword parameters are unsupported.')
        types = parameter_types or {}
        dimensionalities = parameter_dimensionality or {}
        metadata = {
            "id": (name or function_name).upper(),
            "name": (name or function_name).upper(),
            "description": description or inspect.getdoc(function) or function_name,
            "result_type": result_type,
            "result_dimensionality": result_dimensionality,
            "parameters": [
                {
                    "name": parameter_name,
                    "type": types.get(parameter_name, "any"),
                    "dimensionality": dimensionalities.get(parameter_name, "scalar"),
                    **({"repeating": True} if parameter.kind == inspect.Parameter.VAR_POSITIONAL else {}),
                    "optional": parameter.default is not inspect.Parameter.empty,
                }
                for parameter_name, parameter in signature.parameters.items()
            ],
        }
        function.__jupyterexcel_function__ = metadata
        jupyterexcel_functions[function_name] = metadata
        return function

    if _function is None:
        return decorate
    return decorate(_function)


def get_jupyter_functions():
    return list(jupyterexcel_functions.values())


def ribbon_function(name, return_value=None, *, inputs=None, output=None,
                    label=None, button_text='Run', description='', **kwargs):
    if inputs is not None:
        from .actions import action_schema
        schema = action_schema(name, inputs, output, label, button_text, description)
        def decorate(function):
            parameters = list(inspect.signature(function).parameters.values())
            if any(p.kind not in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in parameters):
                raise ValueError('Actions use named positional inputs; use repeatable metadata for lists.')
            if [p.name for p in parameters] != list(inputs):
                raise ValueError('Action inputs must match the function signature in order.')
            function.__jupyterexcel_action__ = schema
            return function
        return decorate
    # Preserve existing VBA-oriented decorator behavior.

    def wrap(function):
        global jupyterexcel_ribbon_functions
        temp_dict ={}
        args = inspect.signature(function)
        i = 1

        for v in args.parameters :
            value = kwargs.get(v, None)
            if not value is None:
               temp_dict[str(i)] =value
            i += 1
        temp_dict['name']=name
        temp_dict['return_value']=return_value
        function_name = function.__name__
        temp_dict['function']=function_name

#        for key, val in kpylv1xxx.items():
#                print('%s %s: %s'%(name, key, val) )
        jupyterexcel_ribbon_functions[function_name] = temp_dict
        print(function_name)
        print(temp_dict)
        return function

    return wrap

def get_ribbon_functions () :
    global jupyterexcel_ribbon_functions
    result =[]
    for d2 in jupyterexcel_ribbon_functions.values() :
        l =['%s=%s'%(k1,v1)  for k1,v1 in d2.items() ]
        result.append(l)
    return result



if __name__ == "__main__":


    @ribbon_function('get_not_so_random_number_with_max', 'Display Result', max_value='Input Integer')
    def get_not_so_random_number_with_max(max_value):
        import random
        return random.random() * max_value

    @ribbon_function('sum', 'Display Result', a='C3', b='D3', c='e3')
    def sum(a, b=0, c=0):
        return float(a) + float(b) +float(c)


#    for key,value in jupyterexcel_ribbon_functions.items() :
#        print ('%s: %s' %(key, ';'.join( [ '%s=%s'%(key2,value2) for key2,value2 in value.items()] ) ) )

    print ( get_not_so_random_number_with_max(100))
    print( sum(1,2,3))

    print (get_ribbon_functions())
#    for d2 in jupyterexcel_ribbon_functions.values() :
#        print (['%s=%s'%(k1,v1)  for k1,v1 in d2.items() ] )
#
