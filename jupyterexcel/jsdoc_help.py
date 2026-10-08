"""Generated reference pages, separate from existing user-maintained help."""
from html import escape
from urllib.parse import quote


def generate_help(batch, functions, namespace):
    directory = batch / 'help' / 'generated'
    directory.mkdir(parents=True, exist_ok=True)
    known = {f.function_id.casefold(): f for f in functions}
    style = '<style>body{font:16px system-ui;max-width:900px;margin:32px auto;padding:0 20px;color:#222}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f6;padding:16px}a{color:#086f8c}input{padding:8px;width:90%}</style>'
    def page(title, content):
        return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(title) + '</title>' + style + '</head><body>' + content + '</body></html>'
    rows = []
    for f in functions:
        if f.kind == 'ribbon' and not f.action:
            continue
        docs = f.documentation
        label = (f.form or f.action or {}).get('label', f.function_id)
        rows.append('<tr><td><a href="generated/' + quote(f.function_id, safe='') + '.html">' + escape(label) + '</a></td><td>' + escape(f.kind) + '</td><td>' + escape(f.execution) + '</td><td>' + escape(f.description) + '</td></tr>')
        parameters = f.parameters
        fields = (f.form or f.action or {}).get('inputs', [])
        parameter_rows = []
        for p in parameters:
            parameter_rows.append('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in
                [p.name, p.type + ('[][]' if p.dimensionality == 'matrix' else ''), 'Optional' if p.optional else 'Required', p.default if p.default is not None else '', p.description]) + '</tr>')
        if not parameters:
            for field in fields:
                parameter_rows.append('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in [field['name'], field['type'], 'Required', field.get('default', ''), field.get('description', field.get('label', ''))]) + '</tr>')
        content = '<a href="../index.html">Function reference</a><h1>' + escape(label) + '</h1><p>' + escape(f.description) + '</p>'
        content += '<p>Identifier: <code>' + escape(f.function_id) + '</code>. Execution: ' + escape(f.execution) + (' (server connection required)' if f.execution == 'server' else ' (Excel add-in)') + '.</p>'
        profile = getattr(f, 'resolved_profile', None) or f.execution_profile
        if profile:
            content += '<p>Execution profile: <code>' + escape(profile) + '</code></p>'
        if f.kind == 'jupyter':
            syntax = '=' + namespace + '.' + f.function_id + '(' + ', '.join('[' + p.name + ']' if p.optional else p.name for p in parameters) + ')'
        else:
            syntax = 'Notebook Actions > ' + label + ' > ' + (f.form or f.action or {}).get('button_text', 'Run')
        content += '<h2>Usage</h2><pre>' + escape(syntax) + '</pre><h2>Parameters</h2><table><tr><th>Name</th><th>Type</th><th>Required</th><th>Default</th><th>Description</th></tr>' + ''.join(parameter_rows) + '</table>'
        result = docs.get('result', (f.action or {}).get('output', {}).get('type', f.result_type))
        content += '<h2>Result</h2><p>' + escape(result + ': ' + docs.get('result_description', '')) + '</p>'
        for key, title in [('remarks', 'Remarks'), ('side_effects', 'Side Effects')]:
            if docs.get(key):
                content += '<h2>' + title + '</h2><p>' + escape(docs[key]) + '</p>'
        for example in docs.get('examples', []):
            content += '<h2>Example</h2><pre>' + escape(example) + '</pre>'
        related = []
        for reference in docs.get('related', []):
            target = known.get(reference.casefold())
            if target:
                related.append('<a href="' + quote(target.function_id, safe='') + '.html">' + escape(reference) + '</a>')
            elif reference.startswith(('https://', 'http://')):
                related.append('<a rel="noopener" href="' + escape(reference, quote=True) + '">' + escape(reference) + '</a>')
            else:
                raise ValueError(f'{f.notebook}: {f.function_id}: unresolved @see {reference}')
        if related:
            content += '<h2>Related</h2><p>' + ' | '.join(related) + '</p>'
        content += '<p>Notebook: ' + escape(f.notebook) + '</p>'
        if f.version:
            content += '<p>Source revision: <code>' + escape(f.version[:12]) + '</code></p>'
        (directory / (f.function_id + '.html')).write_text(page(label, content), encoding='utf-8')
    content = '<h1>Function reference</h1><input id="search" type="search" aria-label="Search functions" placeholder="Search"><table><thead><tr><th>Name</th><th>Kind</th><th>Execution</th><th>Description</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table><script src="search.js"></script>'
    (batch / 'help' / 'index.html').write_text(page('Function reference', content), encoding='utf-8')
    (batch / 'help' / 'search.js').write_text("document.getElementById('search').addEventListener('input', event => { const query = event.target.value.toLowerCase(); for (const row of document.querySelectorAll('tbody tr')) row.hidden = !row.textContent.toLowerCase().includes(query); });", encoding='utf-8')
