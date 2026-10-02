"""Read-only pool telemetry, independent of kernel execution."""
from datetime import datetime, timezone
from tornado import web
try:
    from jupyter_server.base.handlers import APIHandler
    from jupyter_server.auth.decorator import authorized
except ImportError:
    from notebook.base.handlers import APIHandler
    def authorized(**kwargs):
        return lambda method: method


class JupyterStatusHandler(APIHandler):
    def initialize(self, executor, hub_user=None):
        self.executor, self.hub_user = executor, hub_user

    @web.authenticated
    @authorized(action='read', resource='kernels')
    async def get(self):
        self.set_header('Cache-Control', 'no-store')
        if self.hub_user:
            user = self.current_user
            name = user.get('name', user.get('username')) if isinstance(user, dict) else getattr(user, 'username', None)
            if not self.token_authenticated or name != self.hub_user:
                self.set_status(403)
                self.finish({'ok': False, 'error': {'message': 'Use a token for your own Jupyter server.'}})
                return
        from .config import config_report
        response = {'ok': True, 'status': self.executor.status(),
                    'request_id': self.get_query_argument('request_id', ''),
                    'sampled_at': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}
        snapshot = self.settings.get('jupyterexcel_config')
        if snapshot is not None:
            response['configuration'] = config_report(snapshot)
        self.finish(response)
