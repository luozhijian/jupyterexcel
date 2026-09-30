const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
test('status polling renders text and stops when hidden or unauthorized', () => {
  const nodes = {}, messages = [], jobs = new Map(); let id=0, receive;
  function element() { return {hidden:false, children:[], listeners:{}, setAttribute(){}, addEventListener(n,fn){this.listeners[n]=fn;}, appendChild(v){this.children.push(v);}, replaceChildren(){this.children=[];}}; }
  const document = {hidden:false, getElementById(k){return nodes[k] ||= element();}, createElement:element, addEventListener(){}};
  document.getElementById('jupyter-status-panel').hidden = true;
  const Office = {onReady:f=>f(),EventType:{DialogParentMessageReceived:'message'},context:{ui:{messageParent:s=>messages.push(JSON.parse(s)),addHandlerAsync:(event,f)=>receive=f}}};
  vm.runInNewContext(fs.readFileSync('jupyterexcel/addin_template/pool-status-dialog.js','utf8'), {Office,document,window:{location:{origin:'https://assets'},addEventListener(){}},Date,setTimeout:(fn,ms)=>{jobs.set(++id,{fn,ms}); return id;},clearTimeout:id=>jobs.delete(id)});
  nodes['jupyter-status'].onclick();
  const requestId=messages.at(-1).requestId;
  const status = {settings:{max_kernels:4,utilization_window_seconds:5},utilization:.85,queued_requests:2,oldest_wait_seconds:1.2,scaling_status:'Starting a kernel',kernels:[{name:'Kernel 1',status:'busy',utilization:.85,current_function:'<script>x</script>',completed_calls:4,failed_calls:0}]};
  receive({origin:'https://assets',message:JSON.stringify({type:'jupyter-status-result',requestId,status})});
  assert.match(nodes['jupyter-status-summary'].textContent,/85%/);
  assert.equal(nodes['jupyter-status-rows'].children[0].children[3].textContent,'<script>x</script>');
  assert.equal([...jobs.values()][0].ms,2000);
  nodes['jupyter-status'].onclick(); assert.equal(jobs.size,0);
  nodes['jupyter-status'].onclick();
  receive({origin:'https://assets',message:JSON.stringify({type:'jupyter-status-result',requestId:messages.at(-1).requestId,error:'Replace token'})});
  assert.equal(jobs.size,0); assert.equal(nodes['jupyter-status-message'].textContent,'Replace token');
});

test('runtime status uses configured server and saved token without logging credentials', async () => {
  const calls=[];
  const context={URL,AbortController,setTimeout,clearTimeout,console,Date,Math,JSON,Promise,JupyterExcelConfig:{apiBase:'https://server/user/alice'},jupyterExcelAuth:async()=>({token:'secret'}),fetch:async(url,options)=>{calls.push({url,options});return {ok:true,status:200,json:async()=>({ok:true,status:{queued_requests:2}})};}};
  vm.runInNewContext(fs.readFileSync('jupyterexcel/addin_template/jupyter-runtime.js','utf8'),context);
  const status=await context.JupyterExcel.getJupyterStatus();
  assert.equal(status.queued_requests,2);
  assert.equal(calls[0].url,'https://server/user/alice/jupyterexcel/api/status');
  assert.equal(calls[0].options.headers.Authorization,'token secret');
  assert.equal(calls[0].options.credentials,'omit');
});
