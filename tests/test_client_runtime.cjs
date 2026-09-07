const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../jupyterexcel/addin_template/jupyter-runtime.js'), 'utf8');

function context(config = {}, data = new Map()) {
  const calls = [];
  const sandbox = {URL, console, Date, Math, JSON, Promise,
    JupyterExcelConfig: {apiBase:'https://api.example.com/user/alice',hubUser:'alice',hubApiUrl:'https://api.example.com/hub/api/user',...config},
    OfficeRuntime:{storage:{
      getItem: async key => data.get(key),
      setItem: async (key,value) => {data.set(key,value);},
      removeItem: async key => {data.delete(key);}
    }},
    fetch: async (url, options) => {calls.push({url,options}); return {ok:true,status:200,json:async()=>({ok:true,result:42,name:'alice'})};}
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return {sandbox,api:sandbox.JupyterExcel,calls,data};
}

test('DOM-free runtime shares scoped credentials and retains nested arrays', async () => {
  const one = context();
  await one.api.saveAuth({token:'private-token'});
  const two = context({}, one.data);
  assert.equal(await two.api.call('https://api.example.com/user/alice/Excel/SUM', [[1,2],undefined]),42);
  assert.equal(two.calls[0].options.headers.Authorization,'token private-token');
  assert.equal(two.calls[0].options.body,'[[1,2]]');
  assert.equal(two.calls[0].options.credentials,'omit');
  await two.api.flushLogs();
  assert.deepEqual(JSON.parse(JSON.stringify(await two.api.readLogs())),[]);
  assert.equal((await context({apiBase:'https://other.example.com'},one.data).api.readAuth()).token,undefined);
  await assert.rejects(two.api.call('https://evil.example.com/Excel/SUM', []),/outside/);
});

test('single user uses query token and checks the correct identity endpoint', async () => {
  const c = context({hubUser:null,apiBase:'https://api.example.com/base'});
  await c.api.saveAuth({token:'abc+def'});
  await c.api.call('https://api.example.com/base/Excel/ADD',[1,2]);
  assert.equal(new URL(c.calls[0].url).searchParams.get('token'),'abc+def');
  assert.equal(c.calls[0].options.headers.Authorization,undefined);
  assert.equal(c.calls[0].options.headers['Content-Type'],'application/json');
  assert.equal(c.calls[0].options.method,'POST');
  assert.equal(c.calls[0].options.body,'[1,2]');
  await c.api.validateToken('check-me');
  assert.equal(c.calls[1].url,'https://api.example.com/base/api/kernels');
});

test('logging can be enabled, redacts secrets, is bounded and clears across runtimes', async () => {
  const c = context();
  await c.api.writeLogSettings({enabled:true,level:'VERBOSE'});
  c.api.writeLog('INFO','SUM','test','URL ?token=secret',{Authorization:'token secret',password:'password',url:'https://api/?token=secret'});
  c.api.writeLog('INFO','SUM','test','No details');
  await c.api.flushLogs();
  let logs = await c.api.readLogs();
  assert.equal(logs.length,2);
  assert.ok(!JSON.stringify(logs).includes('secret'));
  for (let i=0;i<250;i++) c.api.writeLog('INFO','SUM','test','entry');
  await c.api.flushLogs();
  assert.equal((await c.api.readLogs()).length,200);
  await context({}, c.data).api.clearLogs();
  c.api.writeLog('INFO','SUM','test','after clear');
  await c.api.flushLogs();
  assert.equal((await c.api.readLogs()).length,1);
});

test('storage failure cannot break a worksheet request or leak an exception', async () => {
  const c = context();
  c.sandbox.jupyterExcelAuth = async () => ({token:'hidden'});
  c.sandbox.OfficeRuntime.storage.getItem = async () => {throw new Error('storage failure')};
  assert.equal(await c.api.call('https://api.example.com/user/alice/Excel/SUM',[1]),42);
  await c.api.flushLogs();
});

test('Hub rejects a token belonging to another user', async () => {
  const c = context();
  c.sandbox.fetch = async()=>({ok:true,status:200,json:async()=>({name:'bob'})});
  await assert.rejects(c.api.validateToken('wrong-user'),/different/);
});
