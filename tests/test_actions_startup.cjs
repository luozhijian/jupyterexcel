const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('jupyterexcel/addin_template/actions.js', 'utf8');
function setup() {
  let ready;
  const nodes = {}, logs = [];
  function element() { return {value:'',children:[],classList:{add(){},remove(){}},replaceChildren(){this.children=[];},appendChild(x){this.children.push(x);},add(x){this.children.push(x);if(!this.value)this.value=x.value;},addEventListener(){}}; }
  const sandbox = {document:{getElementById:id=>nodes[id] ||= element(),createElement:element,addEventListener(){}},
    Office:{onReady:fn=>ready=fn,context:{requirements:{isSetSupported:()=>true}}},
    JupyterExcel:{writeLog:(...args)=>logs.push(args)},
    Option:function(label,value){this.textContent=label;this.value=value;},
    fetch:async()=>({ok:true,json:async()=>({version:1,actions:[{id:'TEST',label:'Test action',inputs:[],output:{destinations:['range']}}]})})};
  // Excel is deliberately absent until Office.onReady fires.
  vm.runInNewContext(source, sandbox);
  return {sandbox,nodes,logs,ready:()=>ready()};
}
test('action catalog loads even if Excel selection registration never resolves',async()=>{
  const h = setup(); h.sandbox.Excel={run:()=>new Promise(()=>{})};
  await h.ready();
  assert.equal(h.nodes['action-select'].children.length,1);
  assert.equal(h.nodes['action-select'].value,'TEST');
  assert.ok(h.logs.some(row=>row[2]==='catalog.loaded'));
});
test('selection failure is logged without blocking the catalog',async()=>{
  const h = setup(); h.sandbox.Excel={run:async()=>{throw new Error('Selection unavailable');}};
  await h.ready(); await new Promise(setImmediate);
  assert.equal(h.nodes['action-select'].children.length,1);
  assert.ok(h.logs.some(row=>row[2]==='selection.setup.failed' && row[3]==='Selection unavailable'));
});
