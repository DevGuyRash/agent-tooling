// Bounded transactional IDB double: proves our request/commit contract, not native IndexedDB.
const assert = require('node:assert/strict');
const path = require('node:path');
const copy = value => value === undefined ? undefined : structuredClone(value);
function indexedDBDouble() {
  const records = new Map(), queue = [], calls = [];
  let active = null;
  const factory = { records, calls, failOpen: false, failCommit: false, paused: false,
    open() {
      const request = {};
      setImmediate(() => {
        if (factory.failOpen) { request.onerror?.(); return; }
        request.result = database; request.onupgradeneeded?.(); request.onsuccess?.();
      });
      return request;
    },
    resume() { factory.paused = false; start(); },
  };
  function start() { if (active || factory.paused || !queue.length) return; active = queue.shift(); active.begin(); }
  const database = {
    objectStoreNames: { contains: () => true }, createObjectStore() {}, close() {},
    transaction(name, mode) {
      assert.equal(name, 'records'); assert.ok(['readonly', 'readwrite'].includes(mode));
      let stage, pending = 0, ended = false, started = false;
      const waiting = [];
      const tx = {
        begin() { stage = new Map([...records].map(([key, value]) => [key, copy(value)])); started = true; for (const run of waiting.splice(0)) run(); },
        abort() { if (ended) return; ended = true; setImmediate(() => { tx.onabort?.(); active = null; start(); }); },
        objectStore() { return {
          get(key) { return request('get', key); },
          put(value, key) { assert.equal(mode, 'readwrite'); return request('put', key, value); },
        }; },
      };
      function request(operation, key, value) {
        if (ended) throw Error('Transaction inactive');
        const result = {}; pending++;
        const run = () => setImmediate(() => {
          if (ended) return;
          calls.push([operation, key]);
          if (operation === 'get') result.result = copy(stage.get(key)); else stage.set(key, copy(value));
          result.onsuccess?.(); pending--;
          setImmediate(() => {
            if (ended || pending) return;
            if (mode === 'readwrite' && factory.failCommit) { tx.abort(); return; }
            ended = true;
            if (mode === 'readwrite') { records.clear(); for (const [key, value] of stage) records.set(key, value); }
            tx.oncomplete?.(); active = null; start();
          });
        });
        if (started) run(); else waiting.push(run);
        return result;
      }
      queue.push(tx); setImmediate(start); return tx;
    },
  };
  return factory;
}
function storageWindow(factory = indexedDBDouble(), entries = []) {
  const legacy = new Map(entries), writes = [];
  return { indexedDB: factory, legacy, writes, localStorage: {
    getItem: key => legacy.get(key) ?? null,
    setItem(key, value) { writes.push([key, value]); assert.fail('Legacy bytes must never be overwritten'); },
    removeItem() { assert.fail('Legacy bytes must never be deleted'); },
  } };
}
module.exports = { indexedDBDouble, storageWindow };

async function run(compiled) {
  const { createOwnedStore } = require(path.join(compiled, 'reader-storage.js'));
  const { emptyReaderNotebook, applyReaderDelta, noteVersionIds, encodeReaderNotebook, decodeReaderNotebook, updateReaderState, encodeReaderState } = require(path.join(compiled, 'reader-state.js'));
  const context = { reportId: 'study', revision: 'r1', targetIds: ['a', 'b'], viewIds: ['overview'], journeyIds: [], activityLimit: 128 };
  const owner = { kind: 'notebook', reportId: 'study', revision: 'r1' };
  const at = '2026-09-18T10:00:00Z';
  const change = (book, id, value, targetId = 'a') => ({ epoch: book.epoch, id, change: { type: 'note', targetId, text: value, at }, baseNoteIds: noteVersionIds(book, targetId).slice(-1) });
  const f = indexedDBDouble(), win = storageWindow(f);
  const a = createOwnedStore(win, 'records', owner), b = createOwnedStore(win, 'records', owner);
  assert.equal((await a.read()).value, null); assert.equal((await b.read()).value, null);
  const blank = emptyReaderNotebook(context);
  const results = await Promise.all([
    a.update(current => applyReaderDelta(current || blank, change(blank, 'a1', 'First note'), context)),
    b.update(current => applyReaderDelta(current || blank, { epoch: blank.epoch, id: 'b1', change: { type: 'navigate', viewId: 'overview', mode: 'single', at } }, context)),
  ]);
  assert(results.every(result => result.status === 'saved'));
  assert.equal((await b.read()).value.state.notes[0].text, 'First note', 'Navigation in an old copy cannot remove another copy’s note');
  const common = (await a.read()).value;
  await Promise.all([
    a.update(current => applyReaderDelta(current, change(common, 'a2', 'Edit A'), context)),
    b.update(current => applyReaderDelta(current, change(common, 'b2', 'Edit B'), context)),
  ]);
  const conflicted = (await a.read()).value;
  assert.deepEqual(conflicted.noteVersions.filter(v => v.targetId === 'a').map(v => v.text), ['Edit A', 'Edit B']);
  const exported = encodeReaderNotebook(conflicted, context);
  assert.deepEqual(decodeReaderNotebook(exported, context), conflicted, 'Every competing version survives export/import');
  await Promise.all([
    a.update(current => applyReaderDelta(current, change(conflicted, 'a3', 'Independent target', 'b'), context)),
    b.update(current => applyReaderDelta(current, { epoch: conflicted.epoch, id: 'b3', change: { type: 'bookmark', targetId: 'a', enabled: true, at } }, context)),
  ]);
  const merged = (await a.read()).value;
  assert.equal(merged.state.notes.find(note => note.targetId === 'b').text, 'Independent target'); assert.deepEqual(merged.state.bookmarks, ['a']);
  const recoveredRaw = JSON.stringify(f.records.get('records'));
  const recovered = decodeReaderNotebook(recoveredRaw, context);
  assert.deepEqual(recovered.noteVersions, merged.noteVersions); assert(recovered.originals.includes(recoveredRaw));
  assert.throws(() => decodeReaderNotebook(recoveredRaw, { ...context, reportId:'wrong-report' }), /different record type/);
  for (const foreign of [{ ...owner, reportId: 'other' }, { ...owner, revision: 'r2' }, { ...owner, kind: 'preferences' }]) {
    const wrong = createOwnedStore(win, 'records', foreign);
    assert.equal((await wrong.read()).status, 'blocked'); let invoked = false;
    assert.equal((await wrong.update(() => { invoked = true; return {}; })).status, 'blocked'); assert.equal(invoked, false);
  }
  const beforeFailure = copy(f.records.get('records')); f.failCommit = true;
  assert.equal((await a.update(current => applyReaderDelta(current, change(current, 'fail', 'Not committed'), context))).status, 'unavailable');
  assert.deepEqual(f.records.get('records'), beforeFailure, 'Request success is not transaction success'); f.failCommit = false;
  const legacyState = updateReaderState(blank.state, { type: 'note', targetId: 'a', text: 'Original legacy note', at }, context);
  const raw = ' \n' + encodeReaderState(legacyState) + '\n';
  const legacyWindow = storageWindow(indexedDBDouble(), [['legacy', raw]]);
  const migrated = createOwnedStore(legacyWindow, 'legacy', owner, text => decodeReaderNotebook(text, context));
  assert.equal((await migrated.read()).source, 'legacy'); assert.equal(legacyWindow.indexedDB.records.size, 0, 'Reading never creates a database record');
  const failedMigration = createOwnedStore(storageWindow(indexedDBDouble(), [['legacy', raw]]), 'legacy', owner, text => decodeReaderNotebook(text, context));
  const failedMigrationResult = await failedMigration.update(() => { throw new Error('modeled merge failure'); });
  assert.equal(failedMigrationResult.status, 'blocked'); assert.equal(failedMigrationResult.raw, raw, 'Recovery keeps exact legacy source bytes when migration cannot be combined');
  await migrated.update(current => applyReaderDelta(current, change(current, 'm1', 'Later note', 'b'), context));
  assert.equal(legacyWindow.legacy.get('legacy'), raw); assert.equal(legacyWindow.writes.length, 0);
  const retained = (await migrated.read()).value; assert.deepEqual(retained.originals, [raw]);
  assert.equal(decodeReaderNotebook(encodeReaderNotebook(retained, context), context).originals[0], raw);
  const reduced = decodeReaderNotebook(encodeReaderNotebook(retained, context), { ...context, activityLimit: 0 });
  assert.equal(reduced.state.activity.length, 0); assert.equal(reduced.state.notes.length, 2); assert.equal(reduced.state.nextSequence, retained.state.nextSequence);
  const deletionBase = copy(merged), deletion = change(deletionBase, 'delete-a', '');
  let removed = applyReaderDelta(deletionBase, deletion, context);
  removed = applyReaderDelta(removed, change(deletionBase, 'stale-a', 'Competing with deletion'), context);
  assert(removed.noteVersions.some(version => version.targetId === 'a' && version.text === null));
  assert(removed.noteVersions.some(version => version.text === 'Competing with deletion'));
  assert.deepEqual(decodeReaderNotebook(encodeReaderNotebook(removed, context), context), removed);
  assert.throws(() => applyReaderDelta({ ...removed, epoch:'new-notebook' }, change(removed, 'wrong-epoch', 'Stale copy'), context), /replaced/);
  const broken = copy(removed); broken.noteVersions.push(copy(broken.noteVersions[0]));
  assert.throws(() => decodeReaderNotebook(JSON.stringify(broken), context), /unique/);
  assert.throws(() => decodeReaderNotebook(JSON.stringify({...removed,kind:'preferences'}), context), /kind/);
  assert.throws(() => decodeReaderNotebook(JSON.stringify({...removed,version:99}), context), /version/);
  assert.throws(() => decodeReaderNotebook(JSON.stringify({...removed,state:{...removed.state,notes:[]}}), context), /match/);
  const blockedLegacy = createOwnedStore(legacyWindow, 'legacy', { kind: 'preferences', reportId: 'settings', revision: '1' }, () => ({}));
  assert.equal((await blockedLegacy.update(() => ({}))).status, 'blocked');
  const deniedWindow = storageWindow(undefined, [['reader', raw]]); deniedWindow.indexedDB.failOpen = true;
  const denied = createOwnedStore(deniedWindow, 'reader', owner, text => decodeReaderNotebook(text, context));
  const fallback = await denied.read(); assert.equal(fallback.status, 'unavailable'); assert.equal(fallback.value.state.notes[0].text, 'Original legacy note');
  assert.equal((await denied.update(() => blank)).status, 'unavailable'); assert.equal(deniedWindow.legacy.get('reader'), raw);
  const invalidWindow = storageWindow(indexedDBDouble(), [['broken', ' { invalid json']]);
  const invalid = createOwnedStore(invalidWindow, 'broken', owner, text => decodeReaderNotebook(text, context));
  assert.equal((await invalid.read()).raw, ' { invalid json'); assert.equal((await invalid.update(() => blank)).status, 'blocked');
  const sameKey = storageWindow(), first = createOwnedStore(sameKey, 'claim', owner), second = createOwnedStore(sameKey, 'claim', { ...owner, reportId: 'second' });
  const claims = await Promise.all([first.update(() => blank), second.update(() => blank)]);
  assert.deepEqual(claims.map(result => result.status), ['saved', 'blocked']);
  console.log('reader-storage contracts passed (transaction doubles; native IndexedDB unverified)');
}
if (require.main === module) run(process.argv[2]).catch(error => { console.error(error); process.exitCode = 1; });
