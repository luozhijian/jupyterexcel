const test = require('node:test');
const assert = require('node:assert/strict');
const {eventTouchesInput, createInputMonitor} = require('../jupyterexcel/addin_template/actions.js');
const input = {sheetId:'one', row:1, column:1, rows:2, columns:2, format:true};

test('change filters handle cells, areas, row/column ranges and structural edits', () => {
  for (const address of ['B2', '$C$3', "'Sheet, One'!A1,B2", 'B:B', '2:2']) {
    assert.equal(eventTouchesInput({worksheetId:'one',address},[input]),true,address);
  }
  for (const address of ['A1','D4:E5','D:D','4:4']) {
    assert.equal(eventTouchesInput({worksheetId:'one',address},[input]),false,address);
  }
  assert.equal(eventTouchesInput({worksheetId:'other',address:'B2'},[input]),false);
  assert.equal(eventTouchesInput({worksheetId:'one',address:'B2'},[{...input,format:false}],true),false);
  assert.equal(eventTouchesInput({worksheetId:'one',address:'A1',changeType:'RowInserted'},[input]),true);
  assert.equal(eventTouchesInput({worksheetId:'one',address:''},[input]),true);
});

function mockExcel() {
  const registrations = [], removals = [];
  let activeContext, failFormat = false, failRemove = false;
  const excel = {run: async (context, callback) => {
    if (!callback) { callback = context; context = {sync:async()=>{}, workbook:{worksheets:{getItem:sheetId=>({
      onChanged:{add:fn=>add(sheetId,'value',fn)},
      onFormatChanged:{add:fn=>{ if(failFormat) throw Error('registration failed'); return add(sheetId,'format',fn); }}
    })}}}; }
    activeContext = context;
    return callback(context);
  }};
  function add(sheetId,kind,fn) {
    const context = activeContext;
    const handle = {sheetId,kind,fn,context,remove(){
      assert.equal(activeContext,context);
      if (failRemove) throw Error('remove failed');
      removals.push(handle);
    }};
    registrations.push(handle); return handle;
  }
  return {excel,registrations,removals,setFailFormat:v=>failFormat=v,setFailRemove:v=>failRemove=v};
}

test('paired registrations filter events and remove with their original context', async () => {
  const host=mockExcel(); let invalidated=0, writing=false;
  const monitor=createInputMonitor(host.excel,()=>true,()=>invalidated++,()=>writing);
  await monitor.start([input,{...input,row:6},{...input,sheetId:'two',format:false}]);
  assert.deepEqual(host.registrations.map(h=>[h.sheetId,h.kind]),[['one','value'],['one','format'],['two','value']]);
  host.registrations[0].fn({worksheetId:'one',address:'A1'});
  assert.equal(invalidated,0);
  host.registrations[1].fn({worksheetId:'one',address:'B2'});
  assert.equal(invalidated,1);
  writing=true; host.registrations[0].fn({worksheetId:'one',address:'B2'});
  assert.equal(invalidated,1);
  writing=false;
  const stopped=monitor.stop();
  host.registrations[0].fn({worksheetId:'one',address:'B2'});
  assert.equal(invalidated,1,'late callbacks are inert immediately');
  await stopped;
  assert.equal(host.removals.length,3);
  await monitor.start([input]);
  assert.equal(host.registrations.length,5);
  await monitor.stop();
  assert.equal(host.removals.length,5);
});

test('partial registration failures clean up; failed removals are retried', async () => {
  const host=mockExcel(); const monitor=createInputMonitor(host.excel,()=>true,()=>{});
  host.setFailFormat(true);
  await assert.rejects(monitor.start([input]),/registration failed/);
  assert.equal(host.removals.length,1);
  host.setFailFormat(false);
  await monitor.start([input]);
  host.setFailRemove(true);
  await assert.rejects(monitor.stop(),/remove failed/);
  host.setFailRemove(false);
  await monitor.stop();
  assert.equal(host.removals.length,3);
});

test('rapid start/stop cannot leak registrations or activate obsolete listeners', async () => {
  const host=mockExcel(); const monitor=createInputMonitor(host.excel,()=>true,()=>{});
  const started=monitor.start([input]); const stopped=monitor.stop();
  await Promise.all([started,stopped]);
  assert.equal(host.registrations.length,0);
  await monitor.start([input]);
  const next=monitor.start([{...input,sheetId:'two',format:false}]);
  await next;
  assert.equal(host.removals.length,2);
  assert.equal(host.registrations.at(-1).sheetId,'two');
  await monitor.stop();
});

// Exercise the actual UI callbacks with a minimal DOM and Office host.
async function actionUI() {
  const vm=require('node:vm'), fs=require('node:fs');
  class Element {
    constructor(tag='div') { this.tag=tag; this.children=[]; this.listeners={}; this.value=''; this.classList={add(){},remove(){}}; }
    appendChild(child) { this.children.push(child); return child; }
    prepend(child) { this.children.unshift(child); }
    replaceChildren(...children) { this.children=children; this.value=''; }
    setAttribute() {}
    add(option) { this.children.push(option); if(!this.value) this.value=option.value; }
    addEventListener(name,fn) { this.listeners[name]=fn; }
    removeEventListener(name,fn) { if(this.listeners[name]===fn) delete this.listeners[name]; }
    showModal() { this.open=true; }
    close() { this.open=false; this.listeners.close?.(); }
  }
  const nodes=new Map();
  const $=id=>{ if(!nodes.has(id)) nodes.set(id,new Element()); return nodes.get(id); };
  const registrations=[], removed=[], writes=[];
  let ready, selectedColumn=0;
  const range={load(){},formulas:[['occupied']],address:'Sheet1!D1',get values(){return [[3]];},set values(value){writes.push(value);}};
  const excel={run:async(context,callback)=>{
    if(!callback) {
      callback=context;
      context={sync:async()=>{},workbook:{
        onSelectionChanged:{add(){}},
        getSelectedRange:()=>({load(){},address:selectedColumn ? 'Sheet1!D1' : 'Sheet1!A1',rowIndex:0,columnIndex:selectedColumn,
          rowCount:1,columnCount:1,worksheet:{id:'one',load(){}}}),
        worksheets:{getItem:()=>({
          onChanged:{add(fn){const h={fn,context,remove(){removed.push(h);}}; registrations.push(h); return h;}},
          getRangeByIndexes:(_row,col)=> col===0 ? {load(){},values:[[2]],valueTypes:[['Double']]} : range
        })}
      }};
    }
    return callback(context);
  }};
  const action={id:'Test',label:'Test',inputs:[{name:'data',source:'range',read:['values']}],output:{destinations:['range'],default:'manual'}};
  const sandbox={console,Excel:excel,Office:{onReady:fn=>ready=fn,context:{requirements:{isSetSupported:()=>true}}},
    document:{getElementById:$,createElement:tag=>new Element(tag),addEventListener(){}},
    Option:function(text,value){this.text=text;this.value=value;},
    fetch:async()=>({ok:true,json:async()=>({version:1,actions:[action]})}),
    JupyterExcel:{callAction:async()=>({result:[[7]]})}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../jupyterexcel/addin_template/actions.js'),'utf8'),sandbox);
  await ready();
  const tick=()=>new Promise(resolve=>setImmediate(resolve));
  const input=$('action-inputs').children[0].children[1].children[0];
  input.onclick(); await tick();
  await $('action-run').onclick();
  selectedColumn=3; $('action-target').onclick(); await tick();
  assert.equal($('action-write').disabled,false);
  return {$,registrations,removed,writes,tick,rerun:()=>$('action-run').onclick()};
}

test('cancelled write keeps the result, buttons, and monitoring available', async()=>{
  const ui=await actionUI();
  const pending=ui.$('action-write').onclick(); await ui.tick();
  assert.equal(ui.$('action-dialog').open,true);
  ui.$('action-dialog').close(); await pending;
  assert.equal(ui.writes.length,0);
  assert.equal(ui.removed.length,0);
  assert.equal(ui.$('action-write').disabled,false);
  ui.registrations[0].fn({worksheetId:'one',address:'A1'});
  assert.equal(ui.$('action-write').disabled,true);
});

test('input change during confirmation prevents writing', async()=>{
  const ui=await actionUI();
  const pending=ui.$('action-write').onclick(); await ui.tick();
  ui.registrations[0].fn({worksheetId:'one',address:'A1'});
  const confirm=ui.$('action-dialog-content').children.find(child=>child.tag==='button');
  confirm.onclick(); await pending;
  assert.equal(ui.writes.length,0);
  assert.match(ui.$('action-status').textContent,/changed before writing/);
  assert.equal(ui.$('action-write').disabled,true);
});

test('successful write clears the result and removes monitoring; rerun does not duplicate it', async()=>{
  const ui=await actionUI();
  await ui.rerun();
  assert.equal(ui.removed.length,1);
  const pending=ui.$('action-write').onclick(); await ui.tick();
  ui.registrations.at(-1).fn({worksheetId:'one',address:'Z99'});
  ui.$('action-dialog-content').children.find(child=>child.tag==='button').onclick();
  await pending;
  assert.equal(ui.writes.length,1);
  assert.equal(ui.removed.length,2);
  assert.equal(ui.$('action-write').disabled,true);
});
