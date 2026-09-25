"""Authenticated worksheet execution and generated Office asset routes."""
import json
import getpass
import os
import re

from tornado import web
try:
    from jupyter_server.base.handlers import APIHandler
    from jupyter_server.utils import url_path_join
except ImportError:
    from notebook.base.handlers import APIHandler
    from notebook.utils import url_path_join

from .assets import AssetStore
from .execution import ExecutionError, SharedKernelExecutor
from .reload_handler import ReloadNotebookHandler


class ExcelModeHandler(APIHandler):
    def initialize(self, executor, hub_user=None):
        self.executor, self.hub_user = executor, hub_user

    async def prepare(self):
        print(
            "Excel incoming: method=%s origin=%s requested_headers=%s" %(
            self.request.method,
            self.request.headers.get("Origin"),
            self.request.headers.get("Access-Control-Request-Headers") )
        )
        await super().prepare()

    @web.authenticated
    async def get(self, function_id):
        vv = self.get_query_argument('params', None)
        await self.call(function_id, vv)

    @web.authenticated
    async def post(self, function_id):
        if self.request.headers.get('Content-Type', '').split(';')[0].lower() != 'application/json':
            self.fail(415, 'content_type', 'POST requires application/json.')
            return
        await self.call(function_id, self.request.body)

    async def execute_export(self, function_id, params):
        return await self.executor.execute(function_id, params, idle_only=bool(self.hub_user),
                                           **({"action": False} if self.request.method == "GET" else {}))

    def fail(self, status, code, message):
        self.set_status(status)
        self.finish({'ok': False, 'error': {'code': code, 'message': message}})

    async def call(self, function_id, raw):
        try:
            if self.hub_user:
                if not self.request.headers.get('Authorization', '').lower().startswith(('token ', 'bearer ')):
                    raise ExecutionError(401, 'authentication', 'Hub calls require an Authorization token header.')
                if not self.token_authenticated:
                    raise ExecutionError(401, 'authentication', 'The supplied Hub token was not authenticated.')
                user = self.current_user
                username = user.get('name', user.get('username')) if isinstance(user, dict) else getattr(user, 'username', None)
                if username != self.hub_user:
                    raise ExecutionError(403, 'wrong_user', 'Call the authenticated user\'s own Jupyter server.')
            if not re.fullmatch(r'[A-Za-z0-9._]+', function_id):
                raise ExecutionError(400, 'function_id', 'Invalid exported function ID.')
            if raw is None or len(raw) > 1024 * 1024:
                raise ExecutionError(400, 'params', 'Supply params as a JSON array, at most 1 MiB.')
            try:
                params = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (ValueError, UnicodeError):
                raise ExecutionError(400, 'params', 'Params must be valid JSON.') from None
            if not isinstance(params, list):
                raise ExecutionError(400, 'params', 'Params must be a JSON array.')
            result = await self.execute_export(function_id, params)
            if not result['ok']:
                code = result['error']['code']
                self.set_status(404 if code == 'function_not_found' else 400 if code == 'invalid_arguments' else 500)
            self.finish(result)
        except ExecutionError as error:
            self.fail(error.status, error.code, str(error))
        except Exception:
            self.log.exception('JupyterExcel kernel request failed')
            self.fail(500, 'server_error', 'The server could not complete the kernel request.')


def load_jupyter_server_extension(app):
    settings = app.web_app.settings
    if 'jupyterexcel_asset_store' in settings:
        return

    app.log.info(
    "Effective CORS settings: allow_origin=%r, allow_origin_pat=%r"%(
    app.web_app.settings.get("allow_origin"),
    app.web_app.settings.get("allow_origin_pat"))
    )


    hub_user = os.environ.get('JUPYTERHUB_USER')
    store = AssetStore(app, username=hub_user)
    executor = SharedKernelExecutor(app.kernel_manager, app.session_manager, app.contents_manager,
                                    hub_user or getpass.getuser(), timeout=float(os.environ.get('JUPYTEREXCEL_EXECUTION_TIMEOUT', '30')))
    settings['jupyterexcel_asset_store'] = store
    settings['jupyterexcel_executor'] = executor
    if os.environ.get('JUPYTEREXCEL_KEEP_KERNEL_READY', '').strip().lower() in {'1', 'true', 'yes', 'on'}:
        from .kernel_keeper import KernelKeeper
        keeper = KernelKeeper(executor, app.log)
        keeper.install()
        settings['jupyterexcel_kernel_keeper'] = keeper
        app.log.info('JupyterExcel keep-ready enabled; saved notebooks will initialize automatically.')

    base = settings.get('base_url', '/')

    if base == '/':
        if hub_user:
            #   user/username
             base = '/user/%s/' % hub_user  
    # for hub, it will be forwarded as /hub/Excel/<function_id> and the hub will handle authentication
    match_path =  url_path_join(base,  r'/Excel/([^/]+)')

    app.log.info(f"JupyterExcel: registering {match_path} for Excel function calls (hub_user={hub_user})")
    app.web_app.add_handlers('.*$', [
        (match_path, ExcelModeHandler, {'executor': executor, 'hub_user': hub_user}),
        (url_path_join(base, 'jupyterexcel/api/reload'), ReloadNotebookHandler,
         {'executor': executor, 'store': store, 'hub_user': hub_user}),
    ])

    cm = app.contents_manager
    if hasattr(cm, 'register_post_save_hook'):
        cm.register_post_save_hook(store.schedule)
    else:
        previous = cm.post_save_hook
        def saved(**kwargs):
            try:
                if previous:
                    previous(**kwargs)
            finally:
                store.schedule(**kwargs)
        cm.post_save_hook = saved
    if hasattr(cm, 'event_logger'):
        async def changed(logger, schema_id, data):
            if data.get('action') in {'rename', 'delete', 'copy'}:
                store.schedule()
        cm.event_logger.add_listener(schema_id=cm.event_schema_id, listener=changed)
    store.schedule()
    app.log.info('JupyterExcel loaded; generated assets will be saved under %s', store.root)


def _promote_handler(web_app, handler_cls):
    """Move the rule for handler_cls to the front of its host's rule list
    so it's tried before rules registered by other extensions."""
    try:
        for host_rule in web_app.wildcard_router.rules:
            path_router = host_rule.target          # an _ApplicationRouter
            rules = getattr(path_router, "rules", None)
            if not rules:
                continue
            for i, rule in enumerate(rules):
                if rule.target is handler_cls:
                    rules.insert(0, rules.pop(i))
    except Exception as e:
        app.log.warning("Could not reorder handler %s: %s", handler_cls, e)

_load_jupyter_server_extension = load_jupyter_server_extension
