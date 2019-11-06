# -*- coding: utf-8 -*-


from notebook.utils import url_path_join
from notebook.base.handlers import APIHandler, FilesRedirectHandler, path_regex
from tornado import web, gen
import re
from tornado.gen import maybe_future 
from jupyter_client.kernelspec import NoSuchKernel

#from urllib import parse  #, not what version of ipython is using 

TIMEOUT = 30
saved_nbapp   =None        
   
class ExcelModeHandler(APIHandler):
    #===========================================================================
    cached_dict_bc ={}
    cached_dict_content_last_modified_time ={}
    ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')

    @gen.coroutine    
    @web.authenticated
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
        
    @gen.coroutine          
    def process_request(self, path, query) :
        # copied from jupyter_server/jupyter_server/services/sessions/handlers.py
        global saved_nbapp

#        check if we changed the ipynb file 
        rerun =False
        path = path or ''
        path =path.strip('/')
        if '/' in path :
            path_without_slash =  path.rsplit('/', 1)[1]
        else :
            path_without_slash=path
        content_last_modified_time =self.cached_dict_content_last_modified_time.get(path_without_slash, None)
        
        cached_bc = self.cached_dict_bc.get(path, None)
        if cached_bc == None : 
            try:                
                one_session = yield self.get_session(path_without_slash)
                self.log.info(one_session)
                krnl_model = one_session['kernel']
                krnl_id =krnl_model['id']
                self.log.info('find kernel id %s' % krnl_id )
                krnl= saved_nbapp.kernel_manager.get_kernel(krnl_id)

                cached_bc = krnl.blocking_client()
                self.cached_dict_bc[path] =cached_bc
                self.log.info("get blocking_client: %s"%str(cached_bc))
                self.log.info( vars(cached_bc) )
                rerun =True

            except Exception as ex:
                self.log.error(ex) 
        if not rerun :
            model = self.contents_manager.get(path, content=False)
#            self.log.info( vars(self.contents_manager) )
            if model['last_modified'] != content_last_modified_time:
                rerun = True;
                    
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
                            self.run_code(cached_bc, cell.source)
                            
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
                    self.cached_dict_content_last_modified_time[path] =model['last_modified']
            except Exception as ex:
                self.log.error(ex) 
        try :         
            self.log.debug ('start to get result: ', query)
            msg=self.run_code(cached_bc, 'jptxl_rvxyz=run_function("'+query+'")', user_expressions={'output':'jptxl_rvxyz'} )
            self.log.debug (msg)
            if msg['content']['status'] == 'ok' :
                r = msg['content']['user_expressions']['output']['data']
            else :
                r =msg['content']     #return all content might be easier
                traceback = r.get('traceback', None)
                if traceback: 
                    traceback_2= [  self.ansi_escape.sub('', ttt) for   ttt  in traceback ]
                    r ['traceback'] =traceback_2
#            print ('result: ' , r)
        except Exception as ex:
            #            raise
            r = str(ex)
        
        self.write(r)
       

    def run_code(self, bc, code,user_expressions=None, waitForResult = True):
        # now we can run code.  This is done on the shell channel
        try:
            
#            print ("running:", code)
#            bc.execute(code, user_expressions={'output':'c'} )
            bc.execute(code, user_expressions= user_expressions )
#            msg = bc.get_iopub_msg(block=True, timeout=1)
#            print ('iomessage', msg_execute)
            if waitForResult :
#                execute_message_id = 
                msg = bc.get_shell_msg(block=True)
#                print ("msg", msg)
                return msg

        except Exception as ex: 
            self.log.error(ex)     
            
    @web.authenticated
    def post(self, path=''):
    
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

