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
