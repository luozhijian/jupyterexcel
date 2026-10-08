const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const notebook = JSON.parse(fs.readFileSync('JavaScriptExports.ipynb', 'utf8'));
const notebookSource = notebook.cells.map(c => Array.isArray(c.source) ? c.source.join('') : c.source)
  .find(s => s.includes('@ribbonFunction CREATE_GANTT'));

function setup(rows = [['Plan', 46000, 46002, 0.5]], options = {}) {
  const ranges = new Map(), rules = [], created = [], deleted = [];
  const range = key => {
    if (!ranges.has(key)) ranges.set(key, {format: {font: {}, fill: {}},
      merge() {},
      conditionalFormats: {add() {const r = {custom: {rule: {}, format: {fill: {}}}}; rules.push(r); return r;}}});
    return ranges.get(key);
  };
  const sheet = {getRange: range, getRangeByIndexes: (...v) => range(v.join(',')),
    activate() {}, freezePanes: {freezeAt() {}}, delete() {deleted.push(true);}};
  const source = {load() {return this;}, rowCount: rows.length + 1, columnCount: 4,
    rowIndex: 2, columnIndex: 1, address: "'Project Plan'!B3:E4",
    values: [options.headers || ['Task', 'Start', 'Finish', 'Progress'], ...rows]};
  const inputSheet = {name: "Project's Plan", load() {}, getRange() {return source;}};
  let syncs = 0;
  const context = {async sync() {if (++syncs === options.failAt) throw new Error('Host failure');},
    workbook: {worksheets: {load() {}, getActiveWorksheet: () => inputSheet,
      getItem(name) {assert.equal(name, "Project's Plan"); return inputSheet;},
      items: [{name: 'Gantt'}], add(name) {created.push(name); return sheet;}}}};
  const sandbox = {Office: {context: {requirements: {isSetSupported: () => options.supported !== false}}},
    Excel: {run: fn => fn(context), ConditionalFormatType: {custom: 'Custom'}}};
  vm.runInNewContext(notebookSource, sandbox);
  // Invoke through the production local-export dispatcher; any server call fails.
  vm.runInNewContext(fs.readFileSync('jupyterexcel/addin_template/javascript-exports.js', 'utf8'), sandbox);
  sandbox.JupyterExcel = {call() {throw new Error('Unexpected server call');}};
  sandbox.JupyterExcelJavaScript.register({id: 'CREATE_GANTT', execution: 'local',
    parameters: [{name: 'rangeAddress', type: 'string', optional: true}], output: {type: 'string'}}, sandbox.createGantt);
  return {run: (...args) => sandbox.JupyterExcelJavaScript.call('CREATE_GANTT', args), ranges, rules, created, deleted};
}

test('actual notebook export creates linked, uniquely named Gantt locally', async () => {
  const app = setup();
  assert.match(await app.run(), /Created Gantt 2/);
  assert.deepEqual(app.created, ['Gantt 2']);
  assert.equal(app.rules.length, 4);
  assert.equal(app.ranges.get('4,1,1,2').numberFormat[0][0], 'yyyy-mm-dd');
  assert.equal(app.ranges.get('4,3,1,1').numberFormat[0][0], '0%');
  assert.equal(app.ranges.get('4,0,1,4').formulas[0][0], "='Project''s Plan'!$B$4");
  assert.match(app.rules[0].custom.rule.formula, /\$D5/);
  assert.equal(app.rules[3].custom.rule.formula, '=E$4=TODAY()');
  assert.deepEqual(app.deleted, []);
});
test('invalid inputs never create output sheets', async () => {
  for (const [rows, options, error] of [
    [[], {}, /1-200/], [[['Task', '2026-01-01', 46002, 0]], {}, /Excel dates/],
    [[['Task', 46002, 46000, 0]], {}, /precedes/],
    [[['Task', 46000, 46002, 50]], {}, /Progress/],
    [[['Task', 46000, 47000, 0]], {}, /366/],
    [[['Task', 46000, 46002, 0]], {supported: false}, /ExcelApi/],
    [[['Task', 46000, 46002, 0]], {headers: ['Task']}, /column/]]) {
    const app = setup(rows, options);
    await assert.rejects(app.run(), error);
    assert.deepEqual(app.created, []);
  }
});
test('host error cleans up only the new worksheet', async () => {
  const app = setup(undefined, {failAt: 4});
  await assert.rejects(app.run(), /Host failure/);
  assert.deepEqual(app.created, ['Gantt 2']);
  assert.equal(app.deleted.length, 1);
});
test('qualified addresses support quoted sheet names; malformed addresses fail before writing', async () => {
  const app = setup();
  await app.run("'Project''s Plan'!B3:E4");
  const invalid = setup();
  await assert.rejects(invalid.run('A:A'), /rectangular range/);
  assert.deepEqual(invalid.created, []);
});
