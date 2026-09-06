"""Authenticated worksheet execution and generated Office asset routes."""
import json
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
from .execution import ExecutionError, KernelExecutor


class ExcelModeHandler(APIHandler):
    def initialize(self, executor, hub_user=None):
        self.executor, self.hub_user = executor, hub_user

    @web.authenticated
    async def get(self, function_id):
        await self.call(function_id, self.get_query_argument('inputs', None))

    @web.authenticated
    async def post(self, function_id):
        if self.request.headers.get('Content-Type', '').split(';')[0].lower() != 'application/json':
            self.fail(415, 'content_type', 'POST requires application/json.')
            return
        await self.call(function_id, self.request.body)

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
            if not re.fullmatch(r'[A-Za-z0-9.]+', function_id):
                raise ExecutionError(400, 'function_id', 'Invalid exported function ID.')
            if raw is None or len(raw) > 1024 * 1024:
                raise ExecutionError(400, 'inputs', 'Supply inputs as a JSON array, at most 1 MiB.')
            try:
                inputs = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (ValueError, UnicodeError):
                raise ExecutionError(400, 'inputs', 'Inputs must be valid JSON.') from None
            if not isinstance(inputs, list):
                raise ExecutionError(400, 'inputs', 'Inputs must be a JSON array.')
            result = await self.executor.execute(function_id, inputs, idle_only=bool(self.hub_user))
            if not result['ok']:
                code = result['error']['code']
                self.set_status(404 if code == 'function_not_found' else 400 if code == 'invalid_arguments' else 500)
            self.finish(result)
        except ExecutionError as error:
            self.fail(error.status, error.code, str(error))
        except Exception:
            self.fail(500, 'server_error', 'The server could not complete the kernel request.')


def load_jupyter_server_extension(app):
    settings = app.web_app.settings
    if 'jupyterexcel_asset_store' in settings:
        return
    hub_user = os.environ.get('JUPYTERHUB_USER')
    store = AssetStore(app, username=hub_user)
    executor = KernelExecutor(app.kernel_manager, timeout=float(os.environ.get('JUPYTEREXCEL_EXECUTION_TIMEOUT', '30')))
    settings['jupyterexcel_asset_store'] = store
    settings['jupyterexcel_executor'] = executor
    base = settings.get('base_url', '/')
    app.web_app.add_handlers('.*$', [
        (url_path_join(base, r'/Excel/([^/]+)'), ExcelModeHandler, {'executor': executor, 'hub_user': hub_user}),
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


_load_jupyter_server_extension = load_jupyter_server_extension
