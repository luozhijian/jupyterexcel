const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('jupyterexcel/addin_template/commands.js', 'utf8');
function setup(failure=false) {
 let command, completed=0, closed=0, initialized=false;
 const handlers={};
 const dialog={addEventHandler:(name,fn)=>handlers[name]=fn,close:()=>closed++};
 const Office={onReady:fn=>{initialized=true;fn();},actions:{associate:(_,fn)=>command=fn},AsyncResultStatus:{Succeeded:'ok'},
 EventType:{DialogMessageReceived:'message',DialogEventReceived:'close'},
 context:{ui:{displayDialogAsync:(url,options,cb)=>cb(failure ? {status:'failed',error:{code:12007}} : {status:'ok',value:dialog})}}};
 vm.runInNewContext(source,{Office,URL,window:{location:{href:'https://localhost/commands.html',origin:'https://localhost'}},console:{error:()=>{}}});
 assert.equal(initialized,true, 'command page must initialize Office.js');
 command({completed:()=>completed++});
 return {handlers, completed:()=>completed, closed:()=>closed};
}
test('command stays alive until dialog close and completes once',()=>{
 const s=setup();assert.equal(s.completed(),0);
 s.handlers.close({error:12006});s.handlers.close({error:12006});assert.equal(s.completed(),1);
});
test('close message completes command',async()=>{
 const s=setup();await s.handlers.message({origin:'https://localhost',message:'{"type":"close"}'});
 assert.equal(s.closed(),1);assert.equal(s.completed(),1);
});
test('opening failure completes command',()=>assert.equal(setup(true).completed(),1));

test('ribbon commands switch separate views and complete', async () => {
 const commands = {};
 const elements = Object.fromEntries(['actions-view','debug-view','action-details','action-select','logging-enabled'].map(id => [id,{hidden:false,open:true,focus(){}}]));
 let shown=0, completed=0;
 const Office={onReady:fn=>fn(),addin:{showAsTaskpane:async()=>{shown++;}},actions:{associate:(name,fn)=>commands[name]=fn}};
 vm.runInNewContext(source,{Office,document:{getElementById:id=>elements[id]},console});
 await commands.openNotebookActions({completed:()=>completed++});
 assert.equal(elements['actions-view'].hidden,false);
 assert.equal(elements['debug-view'].hidden,true);
 await commands.openDebugLog({completed:()=>completed++});
 assert.equal(elements['actions-view'].hidden,true);
 assert.equal(elements['debug-view'].hidden,false);
 assert.equal(elements['action-details'].open,false);
 assert.equal(shown,2);
 assert.equal(completed,2);
});

for (const name of ['openNotebookActions', 'openDebugLog']) {
 test(`${name} completes before the task-pane display promise settles`, async () => {
  const commands = {}, errors = [];
  let rejectDisplay, completed = 0;
  const display = new Promise((resolve, reject) => { rejectDisplay = reject; });
  const elements = Object.fromEntries(['actions-view','debug-view','action-details','action-select','logging-enabled'].map(id => [id,{hidden:false,open:true,focus(){}}]));
  const Office = {onReady:fn=>fn(), actions:{associate:(key,fn)=>commands[key]=fn}, addin:{showAsTaskpane:()=>display}};
  vm.runInNewContext(source, {Office, document:{getElementById:id=>elements[id]}, console:{error:(...args)=>errors.push(args)}});
  commands[name]({completed:()=>completed++});
  assert.equal(completed, 1, 'must complete even if display never settles');
  assert.equal(elements['actions-view'].hidden, name === 'openDebugLog');
  assert.equal(elements['debug-view'].hidden, name === 'openNotebookActions');
  rejectDisplay(new Error('display rejected'));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(errors.length, 1);
  assert.equal(errors[0][1], 'display rejected');
  assert.equal(completed, 1, 'late rejection must not complete twice');
 });
 test(`${name} completes if the display call throws synchronously`, () => {
  const commands = {}, errors = [];
  let completed = 0;
  const Office = {onReady:fn=>fn(), actions:{associate:(key,fn)=>commands[key]=fn}, addin:{showAsTaskpane:()=>{throw new Error('display failed');}}};
  vm.runInNewContext(source, {Office, document:{getElementById:()=>({focus(){}})}, console:{error:(...args)=>errors.push(args)}});
  commands[name]({completed:()=>completed++});
  assert.equal(completed, 1);
  assert.equal(errors.length, 1);
 });
}
