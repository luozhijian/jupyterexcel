const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
test('status-only task-pane action reports completion without output controls', async () => {
  class Element {
    constructor() {this.children = []; this.value = ''; this.style = {}; this.classList = {add() {}, remove() {}};}
    replaceChildren(...children) {this.children = children;}
    appendChild(child) {this.children.push(child); return child;}
    add(child) {this.children.push(child); this.value ||= child.value;}
    addEventListener() {}
  }
  const elements = {}, get = id => elements[id] ||= new Element();
  let ready, release;
  const schema = {id: 'CREATE_GANTT', label: 'Create Gantt', inputs: [], javascript: true,
    execution: 'local', output: {status_only: true, destinations: ['taskpane'], default: 'taskpane'}};
  const sandbox = {document: {getElementById: get, createElement: () => new Element(), addEventListener() {}},
    Option: function(text, value) {this.value = value;},
    Office: {onReady: fn => ready = fn, context: {requirements: {isSetSupported: () => true}}},
    Excel: {run: fn => fn({sync: async () => {}, workbook: {onSelectionChanged: {add() {}}}})},
    fetch: async () => ({ok: true, json: async () => ({version: 1, actions: [schema]})}),
    JupyterExcelJavaScript: {call: () => new Promise(resolve => {release = resolve;})}};
  vm.runInNewContext(fs.readFileSync('jupyterexcel/addin_template/actions.js', 'utf8'), sandbox);
  await ready();
  const running = get('action-run').onclick();
  await new Promise(setImmediate);
  assert.equal(get('action-run').disabled, true);
  release('Created Gantt 2.');
  await running;
  assert.equal(get('action-status').textContent, 'Created Gantt 2.');
  assert.equal(get('action-run').disabled, false);
  for (const id of ['action-target-label', 'action-write', 'action-popup', 'action-updates']) {
    assert.equal(get(id).hidden, true);
  }
  assert.equal(get('action-result').children.length, 0);
  const logs = [];
  sandbox.JupyterExcel = {writeLog: (...args) => logs.push(args)};
  sandbox.JupyterExcelJavaScript.call = async () => {throw new Error('Formatting failed');};
  await get('action-run').onclick();
  assert.match(get('action-status').textContent, /Formatting failed/);
  assert.equal(get('action-run').disabled, false);
  assert.ok(logs.some(entry => entry[2] === 'action.failed'));
});
