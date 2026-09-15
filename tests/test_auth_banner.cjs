const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('jupyterexcel/addin_template/taskpane.js','utf8');
function setup(storage = new Map(), blocked = false) {
  const elements = Object.fromEntries(['auth-status-banner','auth-status-dismiss','auth-status-title','auth-status-message'].map(id=>[id,{dataset:{},hidden:false}]));
  let reads=0, removes=0, state='present';
  const context = {
    Office:{onReady(){}},
    document:{getElementById:id=>elements[id]},
    JupyterExcelConfig:{apiBase:'https://server/user/alice/',hubUser:'alice'},
    JupyterExcel:{getAuthStatus:async()=>{if(state==='throw') throw Error('unreadable'); return {state,message:state};}},
    localStorage:{
      getItem(key){reads++; if(blocked) throw Error(); return storage.get(key) ?? null;},
      setItem(key,value){if(blocked) throw Error(); storage.set(key,value);},
      removeItem(key){removes++; if(blocked) throw Error(); storage.delete(key);}
    }
  };
  vm.runInNewContext(source.replace(/\}\)\(\);\s*$/, 'globalThis.testBanner = {refreshAuthStatus, dismissAuthBanner};})();'),context);
  return {...context.testBanner,elements,setState:s=>state=s,reads:()=>reads,removes:()=>removes};
}
test('dismissal persists, preference is read only once, and polling uses memory', async()=>{
  const storage=new Map(), view=setup(storage);
  await view.refreshAuthStatus();
  view.dismissAuthBanner();
  for(let i=0;i<5;i++) await view.refreshAuthStatus();
  assert.equal(view.elements['auth-status-banner'].hidden,true);
  assert.equal(view.reads(),1);
  const reopened=setup(storage);
  await reopened.refreshAuthStatus();
  assert.equal(reopened.elements['auth-status-banner'].hidden,true);
});
test('missing, invalid, unavailable and failed checks clear dismissal and cannot be dismissed',async()=>{
  for(const state of ['missing','failed','unavailable','throw']){
    const storage=new Map(),view=setup(storage);
    await view.refreshAuthStatus(); view.dismissAuthBanner();
    view.setState(state);
    await view.refreshAuthStatus(); view.dismissAuthBanner();
    assert.equal(view.elements['auth-status-banner'].hidden,false);
    assert.equal(view.elements['auth-status-dismiss'].hidden,true);
    assert.equal(storage.size,0);
    await view.refreshAuthStatus();
    assert.equal(view.removes(),1);
    view.setState('present'); await view.refreshAuthStatus();
    assert.equal(view.elements['auth-status-banner'].hidden,false);
    assert.equal(view.elements['auth-status-dismiss'].hidden,false);
    assert.equal(view.reads(),1);
  }
});
test('blocked local storage still supports dismissal and reset in memory',async()=>{
  const view=setup(new Map(),true);
  await view.refreshAuthStatus(); view.dismissAuthBanner();
  await view.refreshAuthStatus();
  assert.equal(view.elements['auth-status-banner'].hidden,true);
  view.setState('missing'); await view.refreshAuthStatus();
  assert.equal(view.elements['auth-status-banner'].hidden,false);
});

