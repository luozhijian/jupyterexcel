# -*- coding: utf-8 -*-


from notebook.utils import url_path_join
from notebook.base.handlers import APIHandler, FilesRedirectHandler, path_regex
from tornado import web, gen
import re
from tornado.gen import maybe_future 
from jupyter_client.kernelspec import NoSuchKernel
from urllib import parse
from enum import Enum
import zmq

class ServerType(Enum):
    NONE =0
    PYTHON = 1
    R = 2
    JULIA = 3


#from notebook.services.config import ConfigManager

#from urllib import parse  #, not what version of ipython is using 

TIMEOUT = 30

saved_nbapp   =None          # keep a copy of app when it starts up


   
class ExcelModeHandler(APIHandler):
    """it is the handler for Jupyter Excel, it will handle post and get and return result
         1). Get input from get or post 
         2). From input url, find the session and kernel and will keep a kernel.blocking client in dictionary for quick lookup
         3). run the code and return result 
    """
    #===========================================================================
    cached_dict_bc ={}  # as static
    cached_dict_content_last_modified_time ={}   # as static
    ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
    count_executeion_for_r = 0  # as static


    @web.authenticated
    @gen.coroutine    
    def get(self, path):
        try :
            self.add_header('Content-Type', 'application/json')
            self.log.info('Excel Mode: %s'% str( self.request))
            self.log.info('path: %s'% path )
#            self.log.info('path: %s'% vars(self) )
#            uri='/Excel/TestingJupyter.ipynb?&functionName=addtwo&1=2&2=101'
#            query = parse.urlsplit(self.request.uri).query  #parse in python 3.xx, avoid to use 
            locationOfQuestionMark = self.request.uri.find('?')
            if locationOfQuestionMark >0 :
                query = self.request.uri [locationOfQuestionMark+1 :]
                self.log.info('query: %s'% query )
                self.process_request (path, query)
            else :
                self.log.info('input is empty')
                
        except Exception as ex:
            self.log.info(str(ex)) 

    @web.authenticated
    @gen.coroutine     
    def post(self, path=''):
        try :   
            self.add_header('Content-Type', 'application/json')
            self.log.info('Excel Mode Post: %s', self.request)
    
            if not self.request.body:
                self.write('input is empty')
                return 
            
            # Do we need to call body.decode('utf-8') here?
            body = self.request.body.strip().decode(u'utf-8')
    #        print(type(body))
    #        print(body)
            self.log.info("post form data: %s" , body)
            
            self.process_request (path, body)
        except Exception as ex:
            self.log.info(str(ex))         
            
    @gen.coroutine        
    def get_session(self, path, kernel_name=None, kernel_id=None, name='') : 
        # copied from jupyter_server/jupyter_server/services/sessions/handlers.py
        sm = self.session_manager 
        name=name or ''
        mtype = 'notebook'
        model=None
        exists = yield maybe_future(sm.session_exists(path=path))
        if exists:
            model = yield maybe_future(sm.get_session(path=path))
        else:
            try:
                model = yield maybe_future(
                    sm.create_session(path=path, kernel_name=kernel_name,
                                      kernel_id=kernel_id, name=name,
                                      type=mtype))
            except NoSuchKernel:
                msg = "The %s '%s' kernel is not available. Please pick another suitable kernel instead, or install that kernel." % (kernel_name, path)
                self.log.warning(msg)
        
        return model
    
    def get_server_type(self, query) :
        if query :
            if 'language=R' in query :
                 return ServerType.R
        return ServerType.PYTHON
        
    @gen.coroutine          
    def process_request(self, path, query) :
        # copied from jupyter_server/jupyter_server/services/sessions/handlers.py
        # main handle 
        global saved_nbapp

#        check if we changed the ipynb file 
        rerun =False   # if should rerun whole ipynb 
        path = path or ''
        path =path.strip('/')
        if '/' in path :
            path_without_slash =  path.rsplit('/', 1)[1]
        else :
            path_without_slash=path
        content_last_modified_time =ExcelModeHandler.cached_dict_content_last_modified_time.get(path_without_slash, None)
        
        (cached_bc, server_type )= ExcelModeHandler.cached_dict_bc.get(path, (None, None))
        
        # finding session, kernel and client 
        if cached_bc == None : 
            try:                
                one_session = yield self.get_session(path_without_slash)
                self.log.info( one_session)
                krnl_model = one_session['kernel']
                server_type =self.get_server_type(query)
                krnl_id =krnl_model['id']
                self.log.info('find %s kernel id %s ' % (str(server_type), krnl_id ) )
                krnl= saved_nbapp.kernel_manager.get_kernel(krnl_id)
                self.log.info( vars(krnl))

                cached_bc = krnl.blocking_client()
                ExcelModeHandler.cached_dict_bc[path] =(cached_bc, server_type)
                self.log.info("get blocking_client: %s"%str(cached_bc))
                self.log.info( vars(cached_bc) )
                rerun =True

            except Exception as ex:
                self.log.error(ex) 
        else :
             self.log.info("find in cache blocking_client: %s"%str(cached_bc))
             
        if not rerun :
            model = self.contents_manager.get(path, content=False)
#            self.log.info( vars(self.contents_manager) )
            if model['last_modified'] != content_last_modified_time:
                rerun = True;
                
        # rerun whole jpynb file when start up             
        if rerun :
            try :  
                model = self.contents_manager.get(path, content=True)
                self.log.debug( model )
                
            except web.HTTPError as e:
                if e.status_code == 404 and 'files' in path.split('/'):
                    # 404, but '/files/' in URL, let FilesRedirect take care of it
                    return FilesRedirectHandler.redirect_to_files(self, path)
                else:
                    raise
                    
            if model['type'] != 'notebook':
                # not a notebook, redirect to files
                return FilesRedirectHandler.redirect_to_files(self, path)

            try :                
                if model['last_modified'] != content_last_modified_time :
                    self.log.info('execute all cells:' + str(model['last_modified']))
                    cells = model['content']['cells']
#                    print("cells", cells)
#                    print("first_cells", cells[0])
                    for cell in cells :
                        if cell.cell_type == 'code' and cell.source.strip():
                            self.run_code(cached_bc, cell.source, waitForResult =True)
                            
                    if server_type == ServerType.PYTHON: 
                        self.run_code_python_related(cached_bc)
                        
                    ExcelModeHandler.cached_dict_content_last_modified_time[path] =model['last_modified']
            except Exception as ex:
                self.log.error(ex) 
                
        # run real function call         
        try :         
            self.log.debug ('start to get result: ', query)
            msg=self.run_code_query(cached_bc, query, server_type)
            r= self.analysis_result(msg, server_type)
        except Exception as ex:
            #            raise
            r = str(ex)
        s = str(r)
        self.log.info('result len %ld:%s'%(len(s), s[:100] ))
        self.write(s)
    
    #--------------------------------------------------------------------------
    # Main run method, deal for difference kernel
    # For python, it use user_expressions to get result
    # For R, it loop use iopub display_data message to get data. 
    #--------------------------------------------------------------------------
    def run_code_query(self, bc, query, server_type = ServerType.PYTHON):
        result =None
        if  server_type == ServerType.PYTHON :
            function_call_string = 'jptxl_rvxyz=run_function("'+query+'")'
            result= self.run_code(bc, function_call_string, user_expressions={'output':'jptxl_rvxyz'} , waitForResult = True, server_type = server_type );
        else :
            function_call_string = self.generate_function_call_string(query) 
            if server_type == ServerType.R :
#                ExcelModeHandler.count_executeion_for_r +=1
#                r_varialbe_name = 'jptxl_rvxyz_%d'% ExcelModeHandler.count_executeion_for_r
#                function_call_string = r_varialbe_name + '  <- ' + function_call_string
                # currently IRKenral do not pass out user_expression:   https://rdrr.io/cran/IRkernel/src/R/execution.r
                # will call display data to get the result 
#                self.run_code(bc, function_call_string, user_expressions=None , waitForResult = True, server_type = server_type );
                result =self.run_code_get_result_from_iopub(bc, function_call_string, user_expressions=None , waitForResult = True, server_type = server_type, requir_display_data =True);
#                if result_0  :
#                    if result_0['msg_type'] != 'error' :
#                        result= self.run_code_get_result_from_iopub(bc, r_varialbe_name, user_expressions=None , waitForResult = True, server_type = server_type, requir_display_data =True);
#                    else :
#                        result = result_0
        
        
        return result;
    
    #--------------------------------------------------------------------------
    # Other than python which can use user_expressions to result back,
    #   for such as R, it should loop iopub to ge display data for that call
    #--------------------------------------------------------------------------
    def run_code_get_result_from_iopub(self, bc, code,user_expressions=None, waitForResult = True, server_type = ServerType.PYTHON, requir_display_data =False) :
        try:
            self.log.info(code)    
            
            poller = zmq.Poller()
            iopub_socket = bc.iopub_channel.socket
            poller.register(iopub_socket, zmq.POLLIN)

            msg =None
            msg_id=bc.execute(code, user_expressions= user_expressions, allow_stdin =False, silent =False, store_history=False )
#            self.log.info(msg_id)
#            self.log.info(vars(bc.iopub_channel))
    
            # wait for output and redisplay it
            while True:

                timeout = 300
                timeout_ms = 1e3 * timeout
                events = dict(poller.poll(timeout_ms))
                if not events:
                    continue
                if iopub_socket not in events:
                    continue
                msg = bc.iopub_channel.get_msg(timeout=0)
#                self.log.debug (msg)      
                msg_type = msg['msg_type']
                if msg['parent_header'].get('msg_id') == msg_id and  ( msg_type== 'display_data'  or msg_type == 'error' or  (not requir_display_data and  msg_type == 'status' and msg['content']['execution_state'] == 'idle' ) ):
                    self.log.info (msg)      
                    break
            bc.get_shell_msg(block=True)  # ignore message
                 
            return msg

        except Exception as ex: 
            self.log.error(ex)     


    
    #--------------------------------------------------------------------------
    #  Run code which do not care about result or for Python style
    #      For python, it will change max_seq_length to 0 to ge all array result, then it will restore it 
    #--------------------------------------------------------------------------
    def run_code(self, bc, code,user_expressions=None, waitForResult = True, server_type = ServerType.PYTHON) :
        # now we can run code.  This is done on the shell channel
        try:
            if waitForResult : 
                if server_type == ServerType.PYTHON :     # for python ,we will make sure, we pass out full array
                    bc.execute('jptxl_backup_max_seq_length = get_ipython().config.PlainTextFormatter.max_seq_length \nget_ipython().config.PlainTextFormatter.max_seq_length =0', user_expressions= None, allow_stdin =False, silent =True, store_history=False )
                    bc.get_shell_msg(block=True)
            self.log.info(code)    
            msg=bc.execute(code, user_expressions= user_expressions, allow_stdin =False, silent =True, store_history=False )
            #self.log.info(msg)
#            msg = bc.get_iopub_msg(block=True, timeout=1)
#            print ('iomessage', msg_execute)
            if waitForResult :
#                execute_message_id = 
                msg = bc.get_shell_msg(block=True)
                #self.log.info(msg)
                if server_type == ServerType.PYTHON :     # for python ,we will make sure, we pass out full array
                    bc.execute('get_ipython().config.PlainTextFormatter.max_seq_length =jptxl_backup_max_seq_length', user_expressions= None, allow_stdin =False, silent =True, store_history=False )
                    bc.get_shell_msg(block=True) # clean up queue

                return msg
            

        except Exception as ex: 
            self.log.error(ex)     

    #--------------------------------------------------------------------------
    #  generate function call from input url 
    #--------------------------------------------------------------------------           
    def generate_function_call_string (self, query)  :
        d = dict(parse.parse_qsl(query) )
        d2={}
        max_parameter_id =0
        for k,v in d.items() :
            if k.isdigit() :
                i =int(k)
                d2[i]= v
                max_parameter_id = max(max_parameter_id, i)
            else :
                d2[k.lower()] =v
            
        if not 'functionname' in d: 
            return 
            
        functionName= d['functionname'] 
        
        function_call_string = functionName + '( '
        
        for i in range(1 , max_parameter_id +1  ) :
            v = d2.get(i, None)
            if v :
                v = '"' + v + '"'
            function_call_string += v if i==1 else (',' +  v ) 
        function_call_string += ')'
        return function_call_string

    #--------------------------------------------------------------------------
    #  for python, there is a easier way to run the function, 
    #--------------------------------------------------------------------------           
    def run_code_python_related(self, cached_bc) :
        invoke_command ='''
from urllib import parse
import inspect

def run_function(query):
    d = dict(parse.parse_qsl(query) )
    d = { k.lower() if isinstance(k, str ) and k != None else k :v for k,v in d.items() }
    if not 'functionname' in d: 
        return 
        
    functionName= d['functionname'] 
    f=globals()[functionName]
    args = inspect.signature(f)
    i =1
    new_d ={}
    for v in args.parameters :
        if str(i) in d:
            new_d[v] = d[str(i)]
        i +=1
        
    return f(**new_d)
        '''
        self.run_code(cached_bc, invoke_command)        
            

    def analysis_result (self, msg, server_type) : 
        if server_type == ServerType.PYTHON :
            if msg['content']['status'] == 'ok' :
                r = msg['content']['user_expressions']['output']['data']
            else :
                r =msg['content']     #return all content might be easier
                traceback = r.get('traceback', None)
                if traceback: 
                    traceback_2= [  self.ansi_escape.sub('', ttt) for   ttt  in traceback ]
                    r ['traceback'] =traceback_2
            #            print ('result: ' , r)
        elif server_type == ServerType.R :
            if 'data' in msg['content'] :
                r2 = msg['content']['data']
                v = r2.get('text/plain', None)
                r = {}
                r ['text/plain'] = v
            else :
                r =msg['content']     #return all content might be easier
                traceback = r.get('traceback', None)
                if traceback: 
                    traceback_2= [  self.ansi_escape.sub('', ttt) for   ttt  in traceback ]
                    r ['traceback'] =traceback_2
            #            print ('result: ' , r)                
        return r
    
    
#===============================================================================
def load_jupyter_server_extension(nbapp):
    global saved_nbapp

    # does not work, because init_webapp() happens before init_server_extensions()
    #nbapp.extra_template_paths.append(tmpl_dir) # dows 
    nbapp.log.info("type of nbapp")
    nbapp.log.info(nbapp)
    saved_nbapp =nbapp
    
#    dir (nbapp)

    web_app = nbapp.web_app
    host_pattern = '.*$'
    route_pattern = url_path_join(web_app.settings['base_url'], r'/Excel%s' % path_regex)
    web_app.add_handlers(host_pattern, [(route_pattern, ExcelModeHandler)])
    nbapp.log.info("Jupyter Excel server extension loaded.")
    nbapp.log.info(web_app)


    