

# -*- coding: utf-8 -*-
"""
Created on Mon Jul  1 22:18:04 2019
reference http://scottlobdell.me/2015/04/decorators-arguments-python/
@author: Administrator
"""
import inspect


#a dictionary to save all cacll back functions

jupyterexcel_ribbon_functions={}


def ribbon_function(name, return_value, **kwargs):
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
