# -*- coding: utf-8 -*-


from notebook.utils import url_path_join
from notebook.base.handlers import IPythonHandler, FilesRedirectHandler, path_regex
from tornado import web

#from urllib import parse  #, not what version of ipython is using 

TIMEOUT = 30
saved_nbapp =None
cached_bc =None
content_last_modified_time =None
    
class ExcelModeHandler(IPythonHandler):
    #===========================================================================
    

    @web.authenticated
    def get(self, path):
        global cached_bc, content_last_modified_time
        rerun =False
        try :
            self.add_header('Content-Type', 'application/json')
            self.log.info('Excel Mode: %s', self.request)
#            uri='/Excel/TestingJupyter.ipynb?&functionName=addtwo&1=2&2=101'
#            query = parse.urlsplit(self.request.uri).query  #parse in python 3.xx, avoid to use 
            uris =self.request.uri.split('?')
            if len(uris) >=2 :
                query = uris[1]
            else :
                self.write('input is empty')
                
            if cached_bc == None : 
                rerun =True
                cm = self.contents_manager
        #        self.log.info(cm)
                km = saved_nbapp.kernel_manager 
        #        self.log.info("type of km: ")
        #        self.log.info(km)
                kernals = km.list_kernel_ids()
                if len(kernals) <=0:
                    kn =km.start_kernel()
                    self.log.info("type of kn: ", str(kn))
    #            km.load_connection_file()
    #            km.start_channels()
    #            connect_shell
    
            
                kernals = km.list_kernel_ids()
                self.log.info("kenerals:" + str(kernals))
                if len(kernals) > 0 :
                    
                    krnl_id =  kernals[0]
                    krnl= km.get_kernel(krnl_id)
                    cached_bc = krnl.blocking_client()
                    self.log.info("type of kernal: ",krnl)
        except :
            raise
        
#        check if we change the file 
        try:
            if not rerun :
                model = cm.get(path, content=True)
                if model['last_modified'] != content_last_modified_time :
                    rerun = True;
        except :
            pass 
        
        if rerun :
            try :  
                model = cm.get(path, content=True)
    
                
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
                    print("cells", cells)
                    print("first_cells", cells[0])
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
                    content_last_modified_time =model['last_modified']
            except :
                raise
        try :         
            print ('start to get result: ', query)
            msg=self.run_code(cached_bc, 'a=run_function("'+query+'")', user_expressions={'output':'a'} )
            print(msg)
            if msg['content']['status'] == 'ok' :
                r = msg['content']['user_expressions']['output']['data']
            else :
                r =msg['content']     #return all content might be easier
#            print ('result: ' , r)
        except Exception as ex:
            #            raise
            r = str(ex)
                
        # fix back button navigation
        self.write(r)
       

    def run_code(self, bc, code,user_expressions=None, waitForResult = True):
        # now we can run code.  This is done on the shell channel
        try:
            
#            print ("running:", code)
#            bc.execute(code, user_expressions={'output':'c'} )
            msg_execute = bc.execute(code, user_expressions= user_expressions )
#            msg = bc.get_iopub_msg(block=True, timeout=1)
#            print ('iomessage', msg_execute)
            if waitForResult :
#                execute_message_id = 
                msg = bc.get_shell_msg(block=True)
#                print ("msg", msg)
                return msg

        except Exception as ex: 
            self.log.error(ex)              

    
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

