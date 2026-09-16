const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
test('built-ins return local configuration without browser, token or network', () => {
  const handlers = {};
  const config = {manifestUrl:'https://example.com/manifest.xml', apiBase:'https://example.com/user/alice', addinVersion:'0.1.0', assetVersion:'20260916010101'};
  const context = {JupyterExcelConfig:config, CustomFunctions:{associate:(id, fn) => handlers[id] = fn}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../jupyterexcel/addin_template/builtin-functions.js'), 'utf8'), context);
  for (const [id, key] of Object.entries({MANIFESTURL:'manifestUrl', SERVERURL:'apiBase', ADDINVERSION:'addinVersion', ASSETVERSION:'assetVersion'})) {
    assert.equal(handlers[id](), config[key]);
  }
  config.assetVersion = 'newer';
  assert.equal(handlers.ASSETVERSION(), '20260916010101');
});
