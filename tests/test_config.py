import copy
import io
import json
import logging
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from jupyterexcel.config import load_config, show_config, config_report
from jupyterexcel.discovery import read_project_config
from jupyterexcel.server_extension import load_jupyter_server_extension


class ConfigurationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'jupyterexcel-config.json'
        self.values = {'server': {'public_url': 'https://api.example/user/alice'},
                       'assets': {'directory': 'assets', 'url': 'https://assets.example/addin'}}
        self.write()
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('JUPYTEREXCEL_CONFIG_FILE', None)

    def write(self):
        self.path.write_text(json.dumps(self.values), encoding='utf-8')

    def test_root_defaults_relative_directory_and_legacy_environment_ignored(self):
        os.environ.update(JUPYTEREXCEL_NAMESPACE='Ignored', JUPYTEREXCEL_EXECUTION_TIMEOUT='999',
                          JUPYTEREXCEL_ASSET_DIR='ignored', JUPYTEREXCEL_PUBLIC_URL='https://ignored')
        snapshot = load_config(root=self.root)
        self.assertEqual(snapshot['path'], str(self.path.resolve()))
        settings = snapshot['config']
        self.assertEqual(settings['assets']['directory'], str(self.root / 'assets'))
        self.assertEqual(settings['addin']['namespace'], 'Jupyter')
        self.assertEqual(settings['execution']['min_kernels'], 1)
        self.assertEqual(settings['execution']['timeout_seconds'], 30)

    def test_central_file_wins_without_merging(self):
        elsewhere = self.root / 'other'
        elsewhere.mkdir()
        (elsewhere / self.path.name).write_text('invalid')
        os.environ['JUPYTEREXCEL_CONFIG_FILE'] = str(self.path)
        snapshot = load_config(root=elsewhere)
        self.assertEqual(snapshot['source'], 'JUPYTEREXCEL_CONFIG_FILE')
        self.assertEqual(snapshot['config']['assets']['directory'], str(self.root / 'assets'))
        for value in ('', 'relative.json', str(self.root / 'missing.json')):
            os.environ['JUPYTEREXCEL_CONFIG_FILE'] = value
            with self.assertRaises(ValueError):
                load_config(root=self.root)

    def test_missing_and_invalid_file_fail_with_path(self):
        for content in ('[]', '{', '{"schema_version": 1, "schema_version": 1}', '{"execution":{"min_kernels":NaN}}'):
            self.path.write_text(content)
            with self.assertRaises(ValueError) as error:
                load_config(root=self.root)
            self.assertIn(str(self.path), str(error.exception))
        self.path.unlink()
        with self.assertRaises(ValueError) as error:
            load_config(root=self.root)
        self.assertIn(str(self.path), str(error.exception))

    def test_schema_validation(self):
        original = copy.deepcopy(self.values)
        cases = [('schema_version', 2), ('schema_version', True), ('unexpected', {}),
                 ('assets', {'directory': '', 'url': 'https://assets.example'}),
                 ('server', {'public_url': 'http://api.example'}),
                 ('server', {'public_url': 'https://user:secret@api.example'}),
                 ('addin', {'namespace': 'bad name'}), ('execution', {'min_kernels': -1}),
                 ('execution', {'min_kernels': True}), ('execution', {'max_kernels': 0.5}),
                 ('execution', {'min_kernels': 5, 'max_kernels': 4}),
                 ('execution', {'keep_kernel_ready': False}),
                 ('hub', {'auto_start_users': 'alice,bob'}),
                 ('discovery', {'include': [{'folder': '../outside'}]})]
        for section, value in cases:
            with self.subTest(section=section, value=value):
                self.values = dict(original, **{section: value})
                self.write()
                with self.assertRaises(ValueError):
                    load_config(root=self.root)

    async def test_startup_snapshot_shared_and_inspection_detects_changes(self):
        cm = SimpleNamespace(root_dir=str(self.root), register_post_save_hook=Mock(),
                             get=lambda *args, **kwargs: {'content': []})
        app = SimpleNamespace(contents_manager=cm, log=logging.getLogger('test'),
                              kernel_manager=object(), session_manager=object(),
                              web_app=SimpleNamespace(settings={}, add_handlers=Mock()))
        with patch('jupyterexcel.assets.AssetStore.schedule'), patch('jupyterexcel.server_extension.ProfileExecutor') as pool:
            load_jupyter_server_extension(app)
            load_jupyter_server_extension(app)
            pool.assert_called_once()
            self.assertEqual(pool.call_args.args[-1]['timeout_seconds'], 30)
            pool.return_value.install.assert_called_once()
        snapshot = app.web_app.settings['jupyterexcel_config']
        self.assertIs(cm._jupyterexcel_config, snapshot)
        store = app.web_app.settings['jupyterexcel_asset_store']
        self.assertIs(store.profile_warnings,
                      app.web_app.settings['jupyterexcel_executor'].profile_warnings)
        self.assertEqual(store.config['server']['public_url'], self.values['server']['public_url'])
        self.values['execution'] = {'min_kernels': 3}
        self.write()
        config, _ = await read_project_config(cm)
        self.assertEqual(config['execution']['min_kernels'], 1)
        config['execution']['min_kernels'] = 4
        self.assertEqual(snapshot['config']['execution']['min_kernels'], 1)
        with redirect_stdout(io.StringIO()) as output:
            report = show_config(server_app=app)
        self.assertTrue(report['restart_required'])
        self.assertIn('loaded server settings', output.getvalue())
        self.assertIn('restart Jupyter', output.getvalue())
        self.path.unlink()
        self.assertTrue(config_report(snapshot)['restart_required'])

    def test_file_preview_is_not_claimed_as_active_server_configuration(self):
        with redirect_stdout(io.StringIO()) as output:
            report = show_config(root=self.root)
        self.assertIn('running server settings not verified', output.getvalue())
        self.assertEqual(report['path'], str(self.path))
