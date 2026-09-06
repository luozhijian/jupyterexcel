"""Generate immutable asset batches and publish a current-batch pointer."""
import asyncio
import json
import os
import re
import shutil
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from jupyter_core.paths import jupyter_data_dir
from .execution import resolved
from .office_addin import scan_notebook, functions_metadata, functions_javascript, public_url


def version_stamp(now):
    digits = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    return f'{now.year % 100:02d}{digits[now.month]}{digits[now.day]}{digits[now.hour]}{now.minute:02d}{now.second:02d}'


class AssetStore:
    def __init__(self, app, template_dir=None, data_dir=None, username=None):
        self.app = app
        self.templates = Path(template_dir or Path(__file__).parent / 'addin_template')
        self.root = Path(data_dir or jupyter_data_dir()) / 'excel-addin'
        if username:
            self.root /= quote(username, safe='').replace('.', '%2E')
        self.username = username
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
        return found

    async def generate(self):
        async with self.lock:
            functions = await self.discover()
            self.root.mkdir(parents=True, exist_ok=True)
            while True:
                version = version_stamp(datetime.now())
                batch = self.root / 'versions' / version
                if not batch.exists():
                    break
                await asyncio.sleep(0.1)
            batch.mkdir(parents=True)
            try:
                # Copy only browser assets, not build configuration or source maps.
                for source in self.templates.rglob('*'):
                    if source.is_file() and source.suffix in {'.html', '.js', '.css', '.png', '.svg', '.xml', '.json'} and source.name != 'package.json':
                        target = batch / source.relative_to(self.templates)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, target)
                base = public_url(self.app)
                script = functions_javascript(functions, base, template_dir=self.templates)
                # Bundle the runtime template and generated registrations for Excel.
                (batch / 'functions.js').write_text(script, encoding='utf-8')
                (batch / 'functions.json').write_text(json.dumps(functions_metadata(functions)), encoding='utf-8')
                for stem in ('functions', 'commands', 'taskpane'):
                    source = batch / (stem + '.js')
                    if source.exists():
                        source.rename(batch / f'{stem}.{version}.js')
                for page in batch.glob('*.html'):
                    content = page.read_text(encoding='utf-8')
                    for stem in ('functions', 'commands', 'taskpane'):
                        content = content.replace(f'{stem}.js', f'{stem}.{version}.js')
                    page.write_text(content, encoding='utf-8')
                # Preserve the extension's current function-list task pane.
                rows = ''.join('<li><code>%s</code> - %s</li>' % (escape(f.function_id), escape(f.description)) for f in functions if f.kind == 'jupyter')
                ribbon = ''.join('<li>%s (%s)</li>' % (escape(f.excel_name), escape(f.notebook)) for f in functions if f.kind == 'ribbon')
                (batch / 'taskpane.html').write_text('<!doctype html><html><head><meta charset="utf-8"><script src="https://appsforoffice.microsoft.com/lib/1/hosted/office.js"></script></head><body><h1>JupyterExcel</h1><h2>Worksheet functions</h2><ul>' + rows + '</ul><h2>Ribbon functions</h2><ul>' + ribbon + '</ul></body></html>', encoding='utf-8')
                manifest = (batch / 'manifest.xml').read_text(encoding='utf-8')
                manifest = manifest.replace('{{FUNCTIONS_SCRIPT}}', f'functions.{version}.js')
                manifest = manifest.replace('/functions.js', f'/functions.{version}.js')
                # Supplied manifest references icon sizes absent from templates.
                for size in (16, 64, 80):
                    if not (batch / 'assets' / f'icon-{size}.png').exists():
                        manifest = manifest.replace(f'icon-{size}.png', 'icon-32.png')
                import xml.etree.ElementTree as ET
                ET.fromstring(manifest)
                (batch / 'manifest.xml').write_text(manifest, encoding='utf-8')
                (batch / '.ready').write_text('complete', encoding='utf-8')
                # A plain static server can serve the output root directly.
                # Publish dependencies first, then the stable manifest last.
                for source in sorted(batch.rglob('*'), key=lambda p: p.name == 'manifest.xml'):
                    if not source.is_file() or source.name.startswith('.'):
                        continue
                    target = self.root / source.relative_to(batch)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name(target.name + '.tmp')
                    shutil.copyfile(source, temporary)
                    os.replace(temporary, target)
                pointer = self.root / 'current.tmp'
                pointer.write_text(json.dumps({'version': version}), encoding='utf-8')
                os.replace(pointer, self.root / 'current.json')
                self.current, self.functions = version, functions
                self.app.log.info('JupyterExcel assets generated: %s', batch)
            except Exception:
                # Incomplete batches are never published or served.
                raise

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
            if len(parts) < 3 or not re.fullmatch(r'[0-9A-Z]{9}', parts[1]):
                raise FileNotFoundError(asset)
            if not (self.root / 'versions' / parts[1] / '.ready').is_file():
                raise FileNotFoundError(asset)
            relative = asset
        else:
            if asset in ('functions.js', 'commands.js', 'taskpane.js'):
                asset = asset.replace('.js', '.' + self.current + '.js')
            relative = 'versions/' + self.current + '/' + asset
        path = (self.root / relative).resolve()
        if not path.is_relative_to((self.root / 'versions').resolve()) or not path.is_file():
            raise FileNotFoundError(asset)
        return path
