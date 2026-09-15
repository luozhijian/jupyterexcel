const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const commands=fs.readFileSync('jupyterexcel/addin_template/commands.js','utf8');
const dialogSource=fs.readFileSync('jupyterexcel/addin_template/token-dialog.js','utf8');
function dialogSetup() {
 const nodes=new Map(), messages=[];
 const document={getElementById(id){if(!nodes.has(id))nodes.set(id,{hidden:false,disabled:false,focus(){},value:''});return nodes.get(id);}};
 let receive;
 const Office={onReady:fn=>fn(),EventType:{DialogParentMessageReceived:'message'},context:{ui:{
   messageParent:text=>messages.push(JSON.parse(text)),
   addHandlerAsync:(type,fn,done)=>{receive=fn;done();}
 }}};
 vm.runInNewContext(dialogSource,{Office,document,JupyterExcelConfig:{apiBase:'https://server/',hubUser:null},window:{location:{origin:'https://assets.example'}}});
 receive({origin:'https://assets.example',message:JSON.stringify({type:'saved',username:'demo'})});
 messages.length=0;
 return {nodes,messages,receive,click:id=>document.getElementById(id).onclick()};
}
test('reload requires confirmation; cancel leaves the runtime untouched',()=>{
 const d=dialogSetup();
 d.click('reload-addin');
 assert.equal(d.nodes.get('reload-confirmation').hidden,false);
 assert.equal(d.messages.length,0);
 d.click('reload-cancel');
 assert.equal(d.nodes.get('reload-confirmation').hidden,true);
 assert.equal(d.messages.length,0);
 d.click('reload-addin'); d.click('reload-confirm'); d.click('reload-confirm');
 assert.deepEqual(d.messages,[{type:'reload-addin'}]);
 d.receive({origin:'https://assets.example',message:'{"type":"reload-error","message":"Try again"}'});
 assert.equal(d.nodes.get('reload-addin').disabled,false);
 assert.equal(d.nodes.get('status').textContent,'Try again');
});
function parentSetup(fail=false) {
 const handlers={},registered={},requests=[],events=[],out=[];
 const dialog={addEventHandler:(id,fn)=>handlers[id]=fn,close:()=>events.push('close'),messageChild:text=>out.push(JSON.parse(text))};
 const Office={onReady:fn=>fn(),actions:{associate:(id,fn)=>registered[id]=fn},AsyncResultStatus:{Succeeded:'ok'},
   EventType:{DialogMessageReceived:'message',DialogEventReceived:'close'},
   context:{ui:{displayDialogAsync:(url,opts,cb)=>cb({status:'ok',value:dialog})}}};
 const window={location:{href:'https://assets.example/taskpane.html',origin:'https://assets.example',reload:()=>events.push('reload')}};
 class DOMParser {parseFromString(){return {querySelectorAll:()=>['functions.js','commands.js','https://appsforoffice.microsoft.com/office.js'].map(src=>({getAttribute:name=>name==='src'?src:null}))};}}
 const fetch=async(url,options)=>{requests.push({url,options}); return {ok:!fail,text:async()=>'<html/>',arrayBuffer:async()=>new ArrayBuffer(0)};};
 vm.runInNewContext(commands,{Office,window,URL,DOMParser,fetch,console});
 registered.openAccessTokenDialog({completed:()=>events.push('completed')});
 return {handlers,requests,events,out};
}
test('parent refreshes local scripts then closes dialog, completes command and reloads',async()=>{
 const p=parentSetup();
 await p.handlers.message({origin:'https://assets.example',message:'{"type":"reload-addin"}'});
 assert.deepEqual(p.events,['close','completed','reload']);
 assert.deepEqual(p.requests.map(r=>r.url),['https://assets.example/taskpane.html','https://assets.example/functions.js','https://assets.example/commands.js']);
 assert.ok(p.requests.every(r=>r.options.cache==='reload'));
});
test('failed fetch or foreign message does not reload or close the dialog',async()=>{
 const p=parentSetup(true);
 await p.handlers.message({origin:'https://untrusted.example',message:'{"type":"reload-addin"}'});
 assert.equal(p.requests.length,0);
 await p.handlers.message({origin:'https://assets.example',message:'{"type":"reload-addin"}'});
 assert.deepEqual(p.events,[]);
 assert.equal(p.out[0].type,'reload-error');
});

