const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const bundle = fs.readFileSync('jupyterexcel/addin_template/sankey.bundle.js', 'utf8');
const data = [['Source','Target','Value'], ['Revenue','Operations',60], ['Revenue','Profit',40], ['Operations','Payroll',60]];
function setup(rows = data) {
  let added = 0, deleted = 0;
  const old = {alternativeTextDescription: 'JupyterExcel:CREATE_SANKEY:2:5', delete() {deleted++;}};
  const unrelated = {alternativeTextDescription: 'Other picture', delete() {throw Error('Wrong image deleted');}};
  const image = {};
  const source = {values: rows, load() {return this;}};
  const cell = {left: 250, top: 30, address: 'Sheet1!F3', load() {return this;}};
  const sheet = {getRangeByIndexes: (r,c,n,m) => n === 1 && m === 1 ? cell : source,
    shapes: {load() {}, items: [old, unrelated], addImage() {added++; return image;}}, activate() {}};
  const draw = {scale() {}, fillRect() {}, fillText() {}, beginPath() {}, moveTo() {}, bezierCurveTo() {}, stroke() {}};
  const sandbox = {document: {createElement: () => ({getContext: () => draw, toDataURL: () => 'data:image/png;base64,TEST'})},
    Office: {context: {requirements: {isSetSupported: () => true}}},
    Excel: {run: fn => fn({sync: async () => {}, workbook: {worksheets: {getItem: () => sheet}}})}};
  vm.runInNewContext(bundle, sandbox);
  return {sandbox, api: sandbox.JupyterExcelCharts, image, counts: () => [added, deleted]};
}
test('Sankey combines duplicate flows and lays out finite proportional links', () => {
  const {api} = setup();
  const graph = api.graphFromRows([...data, ['Revenue','Profit',10]]);
  assert.equal(graph.links.length, 3);
  assert.equal(graph.links.find(l => l.target.id === 'Profit').value, 50);
  assert.ok(graph.links.every(l => Number.isFinite(l.width) && l.width > 0));
});
test('bad data, self-links, and cycles fail', () => {
  const {api} = setup();
  for (const rows of [[['A','B',-1]], [['A','A',1]], [['A','B',1],['B','A',1]], [['A','B','2']]]) {
    assert.throws(() => api.graphFromRows([data[0], ...rows]));
  }
});
test('actual notebook function inserts locally and replaces only owned target image', async () => {
  const app = setup();
  const notebook = JSON.parse(fs.readFileSync('JavaScriptExports.ipynb', 'utf8'));
  const source = notebook.cells.map(c => [].concat(c.source).join('')).find(s => s.includes('@ribbonFunction CREATE_SANKEY'));
  vm.runInNewContext(source, app.sandbox);
  const input = JSON.stringify({sheetId: 'sheet', row: 0, column: 0, rows: 4, columns: 3});
  const target = JSON.stringify({sheetId: 'sheet', row: 2, column: 5, rows: 1, columns: 1});
  assert.match(await app.sandbox.createSankey(input, target), /Sankey created/);
  assert.deepEqual(app.counts(), [1,1]);
  assert.equal(app.image.left, 250);
  assert.equal(app.image.top, 30);
});
test('invalid flows leave existing shapes untouched', async () => {
  const app = setup([data[0], ['A','A',1]]);
  const input = JSON.stringify({sheetId:'s',row:0,column:0,rows:2,columns:3});
  const target = JSON.stringify({sheetId:'s',row:2,column:5,rows:1,columns:1});
  await assert.rejects(app.api.createSankey(input,target), /Self-links/);
  assert.deepEqual(app.counts(), [0,0]);
});
