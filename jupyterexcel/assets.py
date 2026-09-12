"""Generate immutable asset batches and publish a current-batch pointer."""
import asyncio
import hashlib
import tempfile
import json
import os
import re
import shutil
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote, urlsplit

from .execution import resolved
from .office_addin import scan_notebook, functions_metadata, functions_javascript, public_url, client_configuration


def version_stamp(now):
    return now.strftime('%Y%m%d%H%M%S')


class AssetStore:
    def __init__(self, app, template_dir=None, username=None, output_dir=None, asset_url=None):
        self.app = app
        self.templates = Path(template_dir or Path(__file__).parent / 'addin_template')
        # Explicit destinations isolate tests/tools from deployment settings.
        configured = output_dir
        if configured is None:
            configured = os.environ.get('JUPYTEREXCEL_ASSET_DIR')
        if configured is not None:
            if not str(configured).strip():
                raise ValueError('JUPYTEREXCEL_ASSET_DIR/output_dir must be a nonempty absolute path.')
            self.root = Path(configured)
            if not self.root.is_absolute():
                raise ValueError('JUPYTEREXCEL_ASSET_DIR/output_dir must be an absolute path.')
        else:
            raise ValueError('Environment variable JUPYTEREXCEL_ASSET_DIR should be defined for manifest.xml file generation.')
        if self.root.exists() and not self.root.is_dir():
            raise ValueError('Asset output path is not a directory: ' + str(self.root))
        self.username_path = quote(username, safe='').replace('.', '%2E') if username else None
        if self.username_path:
            self.root /= self.username_path
        self.username = username
        self.asset_url = asset_url
        self.current = None
        self.functions = []
        self.lock = asyncio.Lock()
        self.task = None

    async def discover(self):
        found = []
        async def visit(path):
            model = await resolved(self.app.contents_manager.get(path, content=True))
            if model['type'] == 'notebook':
                found.extend(scan_notebook(model['content'], model['path']))
            elif model['type'] == 'directory':
                for child in model.get('content') or []:
                    if child['type'] in ('directory', 'notebook'):
                        await visit(child['path'])
        await visit('')
        ids = [f.function_id for f in found if f.kind == 'jupyter']
        if len(set(ids)) != len(ids) or any(not x for x in ids):
            raise ValueError('Worksheet function IDs must be nonempty and unique.')
        actions = [f.action['id'] for f in found if f.action]
        if len(set(actions)) != len(actions) or set(actions) & set(ids):
            raise ValueError('Function IDs must be unique across worksheet functions and actions.')
        return found

    def _asset_base_url(self):
        configured = self.asset_url
        if configured is None:
            configured = os.environ.get('JUPYTEREXCEL_ASSET_URL')
        if not configured or not str(configured).strip():
            raise ValueError('Environment variable JUPYTEREXCEL_ASSET_URL should be defined for manifest.xml file generation.')
        configured = str(configured).rstrip('/')
        parsed = urlsplit(configured)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('JUPYTEREXCEL_ASSET_URL/asset_url must be an absolute HTTPS URL without query or fragment.')
        return configured + ('/' + self.username_path if self.username_path else '')

    def _render(self, batch, functions):
        # Copy only browser assets, not build configuration or source maps.
        for source in self.templates.rglob('*'):
            if source.is_file() and source.suffix in {'.html', '.js', '.css', '.png', '.svg', '.xml', '.json'} and source.name != 'package.json':
                target = batch / source.relative_to(self.templates)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        (batch / 'actions.json').write_text(json.dumps({'version': 1, 'actions': [
            dict(f.action, notebook=f.notebook) for f in functions if f.action
        ]}), encoding='utf-8')
        base = public_url(self.app)
        script = functions_javascript(functions, base, template_dir=self.templates, hub_user=self.username)
        # Bundle the runtime template and generated registrations for Excel.
        (batch / 'functions.js').write_text(script, encoding='utf-8')
        (batch / 'functions.json').write_text(json.dumps(functions_metadata(functions)), encoding='utf-8')
        (batch / 'jupyter-config.js').write_text('globalThis.JupyterExcelConfig = ' + json.dumps(client_configuration(base, self.username)) + ';\n', encoding='utf-8')
        # Preserve the extension's current function-list task pane.
        rows = ''.join('<li><code>%s</code> - %s</li>' % (escape(f.function_id), escape(f.description)) for f in functions if f.kind == 'jupyter')
        ribbon = ''.join('<li>%s (%s)</li>' % (escape(f.excel_name), escape(f.notebook)) for f in functions if f.kind == 'ribbon')
        taskpane = batch / 'taskpane.html'
        content = taskpane.read_text(encoding='utf-8')
        content = content.replace('{{WORKSHEET_ROWS}}', rows).replace('{{RIBBON_ROWS}}', ribbon)
        taskpane.write_text(content, encoding='utf-8')
        manifest = (batch / 'manifest.xml').read_text(encoding='utf-8')
        manifest = manifest.replace('{{ASSET_BASE_URL}}', self._asset_base_url())
        # Supplied manifest references icon sizes absent from templates.
        for size in (16, 64, 80):
            if not (batch / 'assets' / f'icon-{size}.png').exists():
                manifest = manifest.replace(f'icon-{size}.png', 'icon-32.png')
        import xml.etree.ElementTree as ET
        ET.fromstring(manifest)
        (batch / 'manifest.xml').write_text(manifest, encoding='utf-8')

    @staticmethod
    def _file_hash(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def _inventory(cls, directory):
        return {p.relative_to(directory).as_posix(): cls._file_hash(p)
                for p in sorted(directory.rglob('*'))
                if p.is_file() and not p.name.startswith('.')}

    def _publish_files(self, batch, files):
        for name in sorted(files, key=lambda name: name == 'manifest.xml'):
            target = self.root / name
            if target.is_file() and self._file_hash(target) == files[name]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.tmp')
            shutil.copyfile(batch / name, temporary)
            os.replace(temporary, target)

    def _reuse(self, fingerprint, expected_names):
        try:
            state = json.loads((self.root / 'current.json').read_text(encoding='utf-8'))
            version = state['version']
            files = state['files']
            if state.get('fingerprint') != fingerprint or not re.fullmatch(r'[0-9]{14}', version):
                return False
            expected = set(expected_names)
            if set(files) != expected:
                return False
            batch = self.root / 'versions' / version
            if not (batch / '.ready').is_file():
                return False
            if any(not (batch / name).is_file() or self._file_hash(batch / name) != digest
                   for name, digest in files.items()):
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
        # Restore only missing/modified public files. Never hide write errors by
        # falling back to another directory or updating the success pointer.
        self._publish_files(batch, files)
        self.current = version
        return True

    async def generate(self):
        async with self.lock:
            functions = await self.discover()
            # Render with a fixed placeholder so dates cannot affect comparison.
            # Temporary output is discarded automatically on no-op or failure.
            with tempfile.TemporaryDirectory(prefix='jupyterexcel-build-') as directory:
                staged = Path(directory)
                self._render(staged, functions)
                inventory = self._inventory(staged)
                fingerprint = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
                if self._reuse(fingerprint, inventory):
                    self.functions = functions
                    self.app.log.info('JupyterExcel assets unchanged; existing version %s reused', self.current)
                    return False
                try:
                    self.root.mkdir(parents=True, exist_ok=True)
                except OSError as error:
                    raise OSError(f'Cannot create asset output directory {self.root}: {error}') from error
                while True:
                    version = version_stamp(datetime.now())
                    batch = self.root / 'versions' / version
                    if not batch.exists():
                        break
                    await asyncio.sleep(0.1)
                batch.mkdir(parents=True)
                # Use the exact prepared content so a template edit during the
                # build cannot disagree with the persisted fingerprint.
                for name in inventory:
                    source = staged / name
                    target = batch / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    data = source.read_bytes()
                    target.write_bytes(data)
                files = self._inventory(batch)
                (batch / '.ready').write_text('complete', encoding='utf-8')
                self._publish_files(batch, files)
                state = {'version': version, 'fingerprint': fingerprint, 'files': files}
                pointer = self.root / 'current.tmp'
                pointer.write_text(json.dumps(state, sort_keys=True), encoding='utf-8')
                os.replace(pointer, self.root / 'current.json')
                self.current, self.functions = version, functions
                self.app.log.info('JupyterExcel assets generated: %s', batch)
                return True

    def schedule(self, **kwargs):
        if self.task and not self.task.done():
            self.dirty = True
            return
        async def run():
            while True:
                self.dirty = False
                try:
                    await self.generate()
                except Exception:
                    self.app.log.exception('JupyterExcel asset generation failed; previous batch retained')
                if not self.dirty:
                    break
        self.task = asyncio.get_event_loop().create_task(run())

    def resolve(self, asset):
        if not self.current:
            raise FileNotFoundError('Assets are not ready.')
        asset = asset.removeprefix('public/')
        if asset.startswith('versions/'):
            parts = asset.split('/')
            if len(parts) < 3 or not re.fullmatch(r'(?:[0-9]{14}|[0-9A-Z]{9})', parts[1]):
                raise FileNotFoundError(asset)
            if not (self.root / 'versions' / parts[1] / '.ready').is_file():
                raise FileNotFoundError(asset)
            relative = asset
        else:
            relative = 'versions/' + self.current + '/' + asset
        path = (self.root / relative).resolve()
        if not path.is_relative_to((self.root / 'versions').resolve()) or not path.is_file():
            raise FileNotFoundError(asset)
        return path
