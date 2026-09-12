const test = require('node:test');
const assert = require('node:assert/strict');
const {matrix, excelLiteral, overlaps, parseValue} = require('../jupyterexcel/addin_template/actions.js');
test('return values cannot become formulas', () => {
  for (const text of ['=WEBSERVICE("x")','+1','-1','@SUM(A1)']) assert.equal(excelLiteral(text), "'"+text);
  assert.equal(excelLiteral(12),12); assert.equal(excelLiteral(null),'');
});
test('output overlap is worksheet-specific', () => {
  const a={sheetId:'one',row:0,column:0,rows:3,columns:2};
  assert.equal(overlaps(a,{...a,row:2}),true);
  assert.equal(overlaps(a,{...a,row:3}),false);
  assert.equal(overlaps(a,{...a,sheetId:'two'}),false);
});
test('matrix output rejects malformed or executable structures', () => {
  for (const value of [[],[[1],[2,3]],[[{}]],[[Infinity]]]) assert.throws(()=>matrix(value));
  assert.deepEqual(matrix([[1,'text'],[null,false]]),[[1,'text'],[null,false]]);
});
test('literal A1 remains text and number validation is strict', () => {
  assert.equal(parseValue({type:'text'},{value:'A1'}),'A1');
  assert.throws(()=>parseValue({type:'number'},{value:''}));
  assert.throws(()=>parseValue({type:'number'},{value:'Infinity'}));
});

test('formatted blocks validate shape and preserve, clear, or set fills', () => {
  const {cellBlock,applyFills} = require('../jupyterexcel/addin_template/actions.js');
  const block = {values:[[1,2,3]],format:{fillColors:[[null,'','#FFFF00']]}};
  assert.equal(cellBlock(block),block);
  assert.throws(()=>cellBlock({values:[[1]],format:{fillColors:[['red']]}}));
  assert.throws(()=>cellBlock({values:[[1]],format:{fillColors:[['','']]}}));
  const calls=[];
  const range={getCell:(r,c)=>({format:{fill:{clear:()=>calls.push(['clear',r,c]),set color(v){calls.push(['color',r,c,v]);}}}})};
  applyFills(range,block.format.fillColors);
  assert.deepEqual(calls,[['clear',0,1],['color',0,2,'#FFFF00']]);
});
