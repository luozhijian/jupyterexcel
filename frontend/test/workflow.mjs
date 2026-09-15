import {test} from 'node:test';
import assert from 'node:assert/strict';
import {saveAndReload} from '../lib/workflow.js';

test('waits for save and uses the resulting full notebook path', async () => {
  const events = [];
  let path = 'old.ipynb';
  const result = await saveAndReload(async () => {
    await Promise.resolve(); path = 'nested/renamed.ipynb'; events.push('saved');
  }, () => path, async value => {events.push(value); return 'done';});
  assert.deepEqual(events, ['saved', 'nested/renamed.ipynb']);
  assert.equal(result, 'done');
});
test('save failure never triggers execution', async () => {
  let called = false;
  await assert.rejects(saveAndReload(async () => {throw Error('save failed');}, () => 'a.ipynb',
    async () => {called = true;}), /save failed/);
  assert.equal(called, false);
});
