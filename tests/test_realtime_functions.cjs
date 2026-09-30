const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function harness() {
  let now = new Date(2026, 8, 29, 12).getTime(), id = 0, random = 0;
  const jobs = new Map(), handlers = {};
  class Clock extends Date { constructor(...a) { super(...(a.length ? a : [now])); } static now() { return now; } }
  class CFError extends Error { constructor(code, message) { super(message); this.code = code; } }
  const math = Object.create(Math); math.random = () => (++random % 100) / 100;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../jupyterexcel/addin_template/builtin-functions.js'), 'utf8'), {
    Date: Clock, Math: math, JupyterExcelConfig: {},
    setTimeout(fn, ms) { jobs.set(++id, {fn, at: now + ms}); return id; }, clearTimeout(id) { jobs.delete(id); },
    CustomFunctions: {associate(id, fn) { handlers[id] = fn; }, Error: CFError, ErrorCode: {invalidValue: '#VALUE!', invalidNumber: '#NUM!', notAvailable: '#N/A'}}
  });
  return {handlers, jobs, get now() { return now; }, serial() { return (now - new Date(now).getTimezoneOffset() * 60000) / 86400000 + 25569; },
    tick(ms) { const end = now + ms; while (true) { const next = [...jobs].sort((a,b) => a[1].at-b[1].at)[0]; if (!next || next[1].at > end) break; now = next[1].at; jobs.delete(next[0]); next[1].fn(); } now = end; },
    invoke(name, ...args) { const values = []; const inv = {address: 'Sheet1!A' + (++id), setResult(v) { values.push(v); }}; handlers[name](...args, inv); return {values, cancel() { inv.onCanceled?.(); }}; }
  };
}
test('independent draws share scheduling; last cancellation removes timer', () => {
  const h = harness(), a = h.invoke('RTRAND', 1), b = h.invoke('RTRAND', 1);
  assert.notEqual(a.values[0], b.values[0]); assert.equal(h.jobs.size, 1);
  h.tick(1000); assert.equal(a.values.length, 2); assert.notEqual(a.values[1], b.values[1]);
  a.cancel(); a.cancel(); h.tick(1000); assert.equal(a.values.length, 2); assert.equal(b.values.length, 3);
  b.cancel(); assert.equal(h.jobs.size, 0);
});
test('scheduled start, end, countdown and frozen random values', () => {
  const h = harness(), timer = h.handlers.RTTIMER(h.serial() + 2 / 86400, 1, 2.5 / 60);
  const a = h.invoke('RTRAND', timer), c = h.invoke('RTCOUNTDOWN', timer, undefined);
  assert.equal(a.values[0].code, '#N/A'); h.tick(2000); assert.equal(typeof a.values[1], 'number');
  h.tick(2500); assert.equal(c.values.at(-1), 0); assert.equal(a.values.length, 4); assert.equal(h.jobs.size, 0);
  h.tick(10000); assert.equal(a.values.length, 4);
  const late = h.invoke('RTCOUNTDOWN', timer, undefined); assert.equal(late.values[0], 0); assert.equal(h.jobs.size, 0);
});
test('count, elapsed, date serial, numeric countdown and arrays', () => {
  const h = harness(), c = h.invoke('RTCOUNT', 0.5), e = h.invoke('RTELAPSED', 0.5), n = h.invoke('RTNOW', 1);
  assert.equal(n.values[0], h.serial()); h.tick(1500); assert.deepEqual(c.values, [0,1,2,3]); assert.equal(e.values.at(-1), 1.5);
  const d = h.invoke('RTCOUNTDOWN', 1, 1.5); h.tick(1500); assert.equal(d.values.at(-1), 0);
  const a = h.invoke('RTRANDARRAY', 1, 2, 3, 1, 9, true); assert.equal(a.values[0].length, 2); assert.equal(a.values[0][0].length, 3);
  assert.ok(a.values[0].flat().every(x => Number.isInteger(x) && x >= 1 && x <= 9));
  const defaults = h.invoke('RTRANDARRAY', 1, null, null, null, null, null); assert.equal(defaults.values[0].length, 1);
});
test('invalid arguments do not allocate timers', () => {
  for (const [name, args] of [['RTRAND',[0]], ['RTRAND', [Infinity]], ['RTRAND',['bad']], ['RTRAND',['JupyterExcel.RtTimer.v1:null']], ['RTCOUNTDOWN',[1,undefined]], ['RTRANDBETWEEN',[1,10,1]], ['RTRANDARRAY',[1,100001,1,0,1,false]]]) {
    const h = harness(), a = h.invoke(name, ...args); assert.ok(a.values[0].code, name); assert.equal(h.jobs.size, 0);
  }
});
test('metadata associates every function and requests per-cell streaming context', () => {
  const h = harness(), meta = JSON.parse(fs.readFileSync(path.join(__dirname, '../jupyterexcel/addin_template/builtin-functions.json')));
  for (const f of meta.functions) { assert.equal(typeof h.handlers[f.id], 'function'); if (f.id.startsWith('RT') && f.id !== 'RTTIMER') assert.deepEqual(f.options, {stream:true, requiresStreamAddress:true}); }
});

test('replacement can start before previous cancellation without losing its timer', () => {
  const h = harness(), timer = h.handlers.RTTIMER(h.serial(), 1, 1);
  const old = h.invoke('RTCOUNT', timer), replacement = h.invoke('RTCOUNT', timer);
  old.cancel(); h.tick(1000);
  assert.deepEqual(old.values, [0]); assert.deepEqual(replacement.values, [0,1]);
  replacement.cancel(); assert.equal(h.jobs.size, 0);
});
test('long future schedules chunk timeouts without publishing early', () => {
  const h = harness(), timer = h.handlers.RTTIMER(h.serial() + 30, 1, 1);
  const a = h.invoke('RTCOUNT', timer);
  assert.equal([...h.jobs.values()][0].at - h.now, 2147483647);
  h.tick(2147483647); assert.equal(a.values.length, 1);
  a.cancel(); assert.equal(h.jobs.size, 0);
});
