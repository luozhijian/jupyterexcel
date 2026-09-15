"""Authenticated, explicit notebook reloads from JupyterLab."""
import json
from tornado import web
try:
    from jupyter_server.base.handlers import APIHandler
    from jupyter_server.auth.decorator import authorized
except ImportError:
    from notebook.base.handlers import APIHandler
    def authorized(**kwargs):
        return lambda method: method

from .execution import ExecutionError, resolved


class ReloadNotebookHandler(APIHandler):
    def initialize(self, executor, store, hub_user=None):
        self.executor, self.store, self.hub_user = executor, store, hub_user

    @web.authenticated
    @authorized(action='execute', resource='kernels')
    @authorized(action='read', resource='contents')
    async def post(self):
        try:
            if self.hub_user:
                user = self.current_user
                name = user.get('name', user.get('username')) if isinstance(user, dict) else getattr(user, 'username', None)
                if name != self.hub_user:
                    raise ExecutionError(403, 'wrong_user', 'Reload notebooks on your own Jupyter server.')
            if self.request.headers.get('Content-Type', '').split(';')[0].lower() != 'application/json':
                raise ExecutionError(415, 'content_type', 'Send a JSON notebook path.')
            if len(self.request.body) > 16384:
                raise ExecutionError(400, 'path', 'Notebook path is too long.')
            try:
                body = json.loads(self.request.body)
            except (ValueError, UnicodeError):
                raise ExecutionError(400, 'path', 'Send a JSON notebook path.') from None
            path = body.get('path') if isinstance(body, dict) else None
            if (not isinstance(path, str) or not path.endswith('.ipynb')
                    or '\\' in path or ':' in path or '\x00' in path
                    or any(part in {'', '.', '..'} for part in path.split('/'))):
                raise ExecutionError(400, 'path', 'Supply a notebook path relative to the contents root.')
            model = await resolved(self.executor.contents.get(path, content=True))
            if model['type'] != 'notebook':
                raise ExecutionError(400, 'notebook_required', 'Select a saved notebook.')
            # No-op generation is successful. A publication failure prevents execution.
            changed = await self.store.generate()
            kernel_id = await self.executor.reload_notebook(path)
            self.finish({'ok': True, 'path': path, 'kernel_id': kernel_id,
                         'assets_changed': changed, 'asset_version': self.store.current})
        except ExecutionError as error:
            self.set_status(error.status)
            self.finish({'ok': False, 'error': {'code': error.code, 'message': str(error)}})
        except web.HTTPError as error:
            self.set_status(error.status_code)
            self.finish({'ok': False, 'error': {'code': 'contents_error', 'message': error.reason}})
        except Exception:
            self.log.exception('JupyterExcel save-and-reload failed')
            self.set_status(500)
            self.finish({'ok': False, 'error': {'code': 'reload_failed',
                         'message': 'Save-and-reload failed; inspect the Jupyter server log.'}})
