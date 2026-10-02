import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application
from jupyter_server.auth.identity import IdentityProvider, User
from jupyterexcel.status_handler import JupyterStatusHandler


class Identity(IdentityProvider):
    async def get_user(self, handler):
        header = handler.request.headers.get('Authorization')
        handler._token_authenticated = bool(header)
        return User(username=header.removeprefix('token ')) if header else None


class StatusTests(AsyncHTTPTestCase):
    def get_app(self):
        self.status = Mock(return_value={'queued_requests': 4, 'kernels': [{'status': 'busy'}]})
        self.authorizer = SimpleNamespace(is_authorized=AsyncMock(return_value=True))
        return Application([('/user/alice/jupyterexcel/api/status', JupyterStatusHandler,
                             {'executor': SimpleNamespace(status=self.status), 'hub_user': 'alice'})],
                           identity_provider=Identity(), authorizer=self.authorizer,
                           cookie_secret='test', login_url='/login')

    def test_status_works_without_executing_in_busy_kernels(self):
        response = self.fetch('/user/alice/jupyterexcel/api/status', headers={'Authorization':'token alice'})
        self.assertEqual(response.code, 200)
        self.assertEqual(json.loads(response.body)['status']['queued_requests'], 4)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.status.assert_called_once_with()

    def test_authentication_owner_and_permission(self):
        for headers in ({}, {'Authorization':'token bob'}):
            self.assertEqual(self.fetch('/user/alice/jupyterexcel/api/status', headers=headers).code, 403)
        self.authorizer.is_authorized.return_value = False
        self.assertEqual(self.fetch('/user/alice/jupyterexcel/api/status', headers={'Authorization':'token alice'}).code, 403)
        self.status.assert_not_called()

    def test_configuration_snapshot_is_only_returned_to_owner(self):
        snapshot = {'path': '/missing/settings.json', 'source': 'test',
                    'sha256': 'old', 'config': {'addin': {'namespace': 'Loaded'}}}
        self._app.settings['jupyterexcel_config'] = snapshot
        response = self.fetch('/user/alice/jupyterexcel/api/status', headers={'Authorization': 'token alice'})
        report = json.loads(response.body)['configuration']
        self.assertEqual(report['config']['addin']['namespace'], 'Loaded')
        self.assertTrue(report['restart_required'])
        response = self.fetch('/user/alice/jupyterexcel/api/status', headers={'Authorization': 'token bob'})
        self.assertEqual(response.code, 403)
        self.assertNotIn(b'Loaded', response.body)

    def test_status_echoes_each_request_and_returns_new_counts(self):
        from datetime import datetime
        for request_id, count in [('first', 4), ('second', 5)]:
            self.status.return_value = {'kernels': [{'completed_calls': count}]}
            response = self.fetch('/user/alice/jupyterexcel/api/status?request_id=' + request_id,
                                  headers={'Authorization': 'token alice'})
            body = json.loads(response.body)
            self.assertEqual(body['request_id'], request_id)
            self.assertRegex(body['sampled_at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')
            self.assertIsNotNone(datetime.fromisoformat(body['sampled_at'].replace('Z', '+00:00')).tzinfo)
            self.assertEqual(body['status']['kernels'][0]['completed_calls'], count)
