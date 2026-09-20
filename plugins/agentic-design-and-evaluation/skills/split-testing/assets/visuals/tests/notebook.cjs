// Source-level notebook behavior with explicit DOM doubles. No rendering/browser claims.
const assert = require("node:assert/strict");
const path = require("node:path");
const { researchNotebook, attachNotebooks } = require(path.join(process.argv[2], "notebook.js"));
const { emptyReaderState, updateReaderState, encodeReaderState } = require(path.join(process.argv[2], "reader-state.js"));
const { DocumentDouble, append, send } = require("./dom-double.cjs");
const { enhanceVisuals } = require(path.join(process.argv[2], "interaction.js"));
const { indexedDBDouble, storageWindow } = require("./reader-storage.cjs");
const at = "2026-09-17T18:20:30.000Z";
const passed = [];
async function check(name, body) { await body(); passed.push(name); }
function storage(document, entries = [], factory = indexedDBDouble()) {
  const store = storageWindow(factory, entries);
  document.defaultView.indexedDB = factory; document.defaultView.localStorage = store.localStorage;
  return store;
}
function saved(store, key) { return store.indexedDB.records.get(key)?.value; }
function notebook(parent, scopeId, id, config = {}) {
  const book = append(parent, "details", { id, class: "av-notebook", "data-av-notebook": "", "data-av-notebook-scope": scopeId, "data-av-notebook-revision": config.revision ?? "r1" });
  if (config.key !== undefined) book.setAttribute("data-av-notebook-storage-key", config.key);
  if (config.limit !== undefined) book.setAttribute("data-av-notebook-limit", config.limit);
  append(book, "summary", {}, "Your notebook");
  append(book, "p", { class: "av-notebook-status", "data-av-notebook-status": "", role: "status" }, "Original notebook status");
  const content = append(book, "div", { class: "av-notebook-panel", "data-av-notebook-panel": "", hidden: "" });
  append(content, "span", {}, "Original authored content");
  return book;
}
function report(document, id, config = {}, parent = document.body) {
  const scope = append(parent, "main", { id, class: "av-workspace", "data-av-preferences": "" });
  append(scope, "h1", {}, `${id} report`);
  const views = new Map();
  for (const [view, title] of [["start", "Start <here>"], ["detail", "Full detail"], ["extra", "Other evidence"]]) {
    const node = append(scope, "section", { id: `${id}-${view}`, "data-av-panel": view }); append(node, "h2", {}, title); views.set(view, node);
  }
  const card = append(views.get("detail"), "section", { class: "av-card", id: `${id}-card` }); append(card, "h2", {}, "Source <image> & text");
  const anonymous = append(views.get("detail"), "section", { class: "av-card" }); append(anonymous, "h2", {}, "Unidentified frame");
  append(scope, "nav", { "data-av-journey-id": "intro", "data-av-journey-label": "First reading", "data-av-journey-steps": '["start","detail"]' });
  const book = notebook(config.insideCard ? card : scope, id, `${id}-notebook`, config);
  return { scope, views, card, anonymous, book, context: { reportId: id, revision: config.revision ?? "r1", targetIds: [id, `${id}-start`, `${id}-detail`, `${id}-card`, `${id}-extra`], viewIds: ["start", "detail", "extra"], journeyIds: ["intro"], activityLimit: config.limit ?? 128 } };
}
function controller(root) {
  const calls = { reveals: [], navigations: [] };
  const value = attachNotebooks(root, { now: () => at, reveal: target => calls.reveals.push(target), navigate: (scope, place) => calls.navigations.push({ scope, place }) });
  return { value, calls };
}
const query = (book, selector) => { const value = book.querySelector(selector); assert.ok(value, `Missing ${selector}`); return value; };
const status = book => query(book, "[data-av-notebook-status]").textContent;
const action = (book, name) => query(book, `[data-av-notebook-action="${name}"]`);
function click(controller, book, name) { assert.equal(controller.click(action(book, name)), true); }
function choose(controller, book, targetId) { const target = query(book, "[data-av-notebook-target]"); target.value = targetId; assert.equal(controller.change(target), true); }
function draft(controller, book, text) { const note = query(book, "[data-av-notebook-note]"); note.value = text; assert.equal(controller.input(note), true); }
function bookmark(controller, book, enabled) { const target = query(book, "[data-av-notebook-bookmark]"); target.checked = enabled; assert.equal(controller.change(target), true); }
async function download(controller, book, recovery = false) {
  click(controller, book, recovery ? "recover" : "export");
  await controller.whenIdle();
  const href = action(book, recovery ? "recover" : "download").getAttribute("href");
  assert.match(href, /^data:application\/json;charset=utf-8,/);
  return decodeURIComponent(href.slice(href.indexOf(",") + 1));
}
async function exported(controller, book) { return JSON.parse(await download(controller, book)); }
function stateWith(context, changes) {
  let state = emptyReaderState(context);
  for (const change of changes) state = updateReaderState(state, { at, ...change }, context);
  return state;
}
async function importFile(controller, book, raw, name = "reader.json") {
  const input = query(book, "[data-av-notebook-import]"); input.files = [{ name, text: async () => raw }];
  assert.equal(controller.change(input), true);
  await Promise.resolve(); await Promise.resolve();
}



(async () => {
  await check("renderer is escaped and validates identities and retention inputs", () => {
    const html = researchNotebook({ id: "book:a", scopeId: "report-1", revision: 'r"<&', storageKey: 'saved"<&', activityLimit: 0 });
    assert.match(html, /^<details class="av-notebook"/); assert.match(html, /data-av-notebook-panel hidden/);
    assert.match(html, /data-av-notebook-revision="r&quot;&lt;&amp;"/); assert.doesNotMatch(html, /<script|onclick=/);
    for (const patch of [{ id: "bad id" }, { scopeId: "#scope" }, { revision: "" }, { storageKey: "" }, { activityLimit: -1 }, { activityLimit: .5 }]) assert.throws(() => researchNotebook({ id: "book", scopeId: "report", revision: "r1", ...patch }));
  });
  await check("session notebooks never access unrequested storage and export exact drafts without save events", async () => {
    const d = new DocumentDouble(), f = report(d, "session");
    Object.defineProperty(d.defaultView, "localStorage", { get() { assert.fail("No storage requested"); } });
    Object.defineProperty(d.defaultView, "indexedDB", { get() { assert.fail("No database requested"); } });
    const { value: api } = controller(f.scope); await api.whenIdle(); assert.equal(api.restore(f.scope), null);
    choose(api, f.book, "session-card"); draft(api, f.book, "  <script> & 日本語\n0  ");
    choose(api, f.book, "session-start"); draft(api, f.book, "Second draft");
    choose(api, f.book, "session-card"); assert.equal(query(f.book, '[data-av-notebook-note]').value, "  <script> & 日本語\n0  ");
    const transfer = await exported(api, f.book); assert.equal(transfer.version, 3); assert.equal(transfer.state.notes.length, 2); assert.deepEqual(transfer.state.activity, []);
    draft(api, f.book, 'Changed after preparation'); assert.equal(action(f.book, 'download').hidden, true, 'Editing invalidates an earlier prepared download');
    click(api, f.book, "save-note"); assert.equal((await exported(api, f.book)).state.activity[0].action, "note-saved");
    assert.match(status(f.book), /open report/); api.cleanup();
  });
  await check("legacy migration keeps exact originals, restores once asynchronously and trims only history", async () => {
    const d = new DocumentDouble(), f = report(d, "legacy", { key: "reader", limit: 0 });
    const full = { ...f.context, activityLimit: 128 };
    let state = emptyReaderState(full);
    state = updateReaderState(state, { type: "note", targetId: "legacy-card", text: "Original text", at }, full);
    state = updateReaderState(state, { type: "navigate", viewId: "detail", mode: "all", journeyId: "intro", at }, full);
    const raw = " \n" + encodeReaderState(state) + "\n", store = storage(d, [["reader", raw]]);
    const { value: api, calls } = controller(f.scope); assert.equal(api.restore(f.scope), null); await api.whenIdle();
    assert.equal(store.indexedDB.records.size, 0); assert.equal(calls.navigations.length, 1); assert.equal(api.restore(f.scope).mode, "all");
    assert.deepEqual((await exported(api, f.book)).state.notes, state.notes); assert.equal((await exported(api, f.book)).state.activity.length, 0);
    choose(api, f.book, "legacy-start"); bookmark(api, f.book, true); await api.whenIdle();
    assert.equal(saved(store, "reader").state.notes[0].text, "Original text"); assert.equal(store.legacy.get("reader"), raw);
    assert.deepEqual(saved(store, "reader").originals, [raw]); assert.equal(store.writes.length, 0); api.cleanup();
  });
  await check("ordinary navigation cannot erase another open copy's notes and independent edits merge", async () => {
    const factory = indexedDBDouble(), d1 = new DocumentDouble(), d2 = new DocumentDouble();
    const a = report(d1, "same", { key: "reader" }), b = report(d2, "same", { key: "reader" });
    const store = storage(d1, [], factory); storage(d2, [], factory);
    const ca = controller(a.scope).value, cb = controller(b.scope).value; await Promise.all([ca.whenIdle(), cb.whenIdle()]);
    choose(ca, a.book, "same-card"); draft(ca, a.book, "A's note"); click(ca, a.book, "save-note"); await ca.whenIdle();
    cb.recordPlace(b.scope, { viewId: "detail", mode: "single", journeyId: null }); await cb.whenIdle();
    assert.equal(saved(store, "reader").state.notes[0].text, "A's note");
    choose(ca, a.book, "same-start"); draft(ca, a.book, "Different target"); click(ca, a.book, "save-note");
    choose(cb, b.book, "same-extra"); bookmark(cb, b.book, true); await Promise.all([ca.whenIdle(), cb.whenIdle()]);
    const next = saved(store, "reader"); assert.equal(next.state.notes.length, 2); assert(next.state.bookmarks.includes("same-extra"));
    ca.cleanup(); cb.cleanup();
  });
  await check("same-note edits and removals retain competing versions until explicit resolution", async () => {
    const factory = indexedDBDouble(), d1 = new DocumentDouble(), d2 = new DocumentDouble();
    const a = report(d1, "conflict", { key: "reader" }), b = report(d2, "conflict", { key: "reader" });
    const store = storage(d1, [], factory); storage(d2, [], factory);
    const ca = controller(a.scope).value, cb = controller(b.scope).value; await Promise.all([ca.whenIdle(), cb.whenIdle()]);
    choose(ca, a.book, "conflict-card"); choose(cb, b.book, "conflict-card");
    draft(ca, a.book, "Version A"); draft(cb, b.book, "Version B"); click(ca, a.book, "save-note"); click(cb, b.book, "save-note");
    await Promise.all([ca.whenIdle(), cb.whenIdle()]);
    assert.deepEqual(saved(store, "reader").noteVersions.map(v => v.text), ["Version A", "Version B"]);
    const copyA = await exported(ca, a.book); assert.equal(copyA.noteVersions.length, 2, "Export refresh includes competing edits from the other copy");
    assert.match(query(a.book, '[data-av-notebook-conflicts]').textContent, /Version A.*Version B/s);
    const resolve = query(a.book, '[data-av-notebook-action="resolve-note"]'); ca.click(resolve); await ca.whenIdle();
    assert.equal(saved(store, "reader").noteVersions.length, 1); assert.equal(saved(store, "reader").state.notes[0].text, "Version A");
    draft(cb, b.book, "A stale competing edit"); click(cb, b.book, "save-note"); await cb.whenIdle();
    assert.equal(saved(store, "reader").noteVersions.length, 2, "Resolving known versions cannot erase a later stale edit");
    ca.cleanup(); cb.cleanup();
  });
  await check("independent root key collisions cannot replace another report or a preference envelope", async () => {
    const d = new DocumentDouble(), factory = indexedDBDouble(), store = storage(d, [], factory);
    const a = report(d, "report-a", { key: "shared" }), b = report(d, "report-b", { key: "shared" });
    const ca = controller(a.scope).value, cb = controller(b.scope).value; await Promise.all([ca.whenIdle(), cb.whenIdle()]);
    draft(ca, a.book, "Keep report A"); click(ca, a.book, "save-note"); await ca.whenIdle();
    cb.recordPlace(b.scope, { viewId: "start", mode: "single", journeyId: null }); await cb.whenIdle();
    assert.equal(saved(store, "shared").state.reportId, "report-a"); assert.match(status(b.book), /another record type, report or revision/);
    assert.equal((await exported(cb, b.book)).state.reportId, "report-b"); assert.match(await download(cb, b.book, true), /Keep report A/);
    ca.cleanup(); cb.cleanup();
  });
  await check("unavailable IDB and aborted commits visibly preserve records and drafts for export", async () => {
    const d = new DocumentDouble(), f = report(d, "failure", { key: "reader" }), store = storage(d);
    store.indexedDB.failOpen = true; const api = controller(f.scope).value;
    draft(api, f.book, "Typed during loading"); click(api, f.book, "save-note"); await api.whenIdle();
    assert.match(status(f.book), /unavailable|failed|could not/); assert.equal((await exported(api, f.book)).state.notes[0].text, "Typed during loading"); api.cleanup();
    const e = new DocumentDouble(), g = report(e, "quota", { key: "reader" }), failed = storage(e), b = controller(g.scope).value; await b.whenIdle();
    failed.indexedDB.failCommit = true; draft(b, g.book, "Quota-safe note"); click(b, g.book, "save-note"); await b.whenIdle();
    assert.equal(failed.indexedDB.records.size, 0); assert.equal((await exported(b, g.book)).state.notes[0].text, "Quota-safe note"); assert.doesNotMatch(status(g.book), /Saved in this browser/); b.cleanup();
  });
  await check("corrupt legacy records remain downloadable and reset/import cannot overwrite them", async () => {
    const d = new DocumentDouble(), f = report(d, "protected", { key: "reader" }), raw = " \n{broken", store = storage(d, [["reader", raw]]), api = controller(f.scope).value; await api.whenIdle();
    draft(api, f.book, "Session-only note"); click(api, f.book, "save-note");
    assert.equal(await download(api, f.book, true), raw); assert.equal((await exported(api, f.book)).state.notes[0].text, "Session-only note");
    click(api, f.book, "start-reset"); click(api, f.book, "cancel-reset"); assert.equal((await exported(api, f.book)).state.notes.length, 1);
    click(api, f.book, "start-reset"); click(api, f.book, "confirm-reset"); await api.whenIdle();
    assert.equal((await exported(api, f.book)).state.notes.length, 0); assert.equal(store.legacy.get("reader"), raw); assert.equal(store.indexedDB.records.size, 0); api.cleanup();
  });
  await check("old/new imports require confirmation, preserve conflicts, and ignore stale asynchronous reads", async () => {
    const d = new DocumentDouble(), f = report(d, "imports"), api = controller(f.scope).value;
    draft(api, f.book, "Current draft");
    const old = stateWith(f.context, [{ type: "note", targetId: "imports-card", text: "Old-format note" }]);
    await importFile(api, f.book, encodeReaderState(old)); assert.equal(action(f.book, "confirm-import").hidden, false);
    assert.equal((await exported(api, f.book)).state.notes[0].text, "Current draft"); click(api, f.book, "cancel-import");
    await importFile(api, f.book, encodeReaderState(old)); click(api, f.book, "confirm-import");
    const migrated = await exported(api, f.book); assert.equal(migrated.state.notes[0].text, "Old-format note"); assert.equal(migrated.originals[0], encodeReaderState(old));
    await importFile(api, f.book, JSON.stringify(migrated)); click(api, f.book, "confirm-import"); assert.equal((await exported(api, f.book)).state.notes[0].text, "Old-format note");
    await importFile(api, f.book, "not JSON"); assert.equal(action(f.book, "confirm-import").hidden, true);
    const input = query(f.book, '[data-av-notebook-import]'); let finish;
    input.files = [{ name: "slow.json", text: () => new Promise(resolve => { finish = resolve; }) }]; api.change(input); click(api, f.book, "cancel-import"); finish(JSON.stringify(migrated)); await Promise.resolve(); await Promise.resolve();
    assert.equal(action(f.book, "confirm-import").hidden, true);
    input.files = [{ name: "unreadable.json", text: () => Promise.reject(Error("private diagnostic")) }]; api.change(input); await Promise.resolve(); await Promise.resolve();
    assert.match(status(f.book), /could not be read/); assert.doesNotMatch(status(f.book), /private diagnostic/); api.cleanup();
  });
  await check("nested ownership, repeated labels and moved live frames preserve note targets", async () => {
    const d = new DocumentDouble(), outer = report(d, "outer", { insideCard: true }), inner = report(d, "inner", {}, outer.scope);
    const duplicate = append(outer.views.get('start'), 'section', { class:'av-card', id:'another-card' }); append(duplicate, 'h2', {}, 'Source <image> & text');
    const api = controller(outer.scope).value;
    const options = query(outer.book, '[data-av-notebook-target]').options;
    assert(!options.some(option => option.value === 'inner-card')); assert.equal(new Set(options.map(option => option.textContent)).size, options.length);
    choose(api, outer.book, 'outer-card'); const dialog = append(d.body, 'dialog'); dialog.appendChild(outer.card);
    draft(api, outer.book, 'Moved live target'); click(api, outer.book, 'save-note');
    assert.equal((await exported(api, outer.book)).state.notes[0].targetId, 'outer-card');
    choose(api, inner.book, 'inner-card'); draft(api, inner.book, 'Inner note'); click(api, inner.book, 'save-note');
    assert.equal((await exported(api, inner.book)).state.notes[0].text, 'Inner note'); api.cleanup();
  });
  await check("cleanup cancels late restore, keeps queued saves and retains unsaved drafts on reattachment", async () => {
    const d = new DocumentDouble(), f = report(d, 'cleanup', {key:'reader'}), store = storage(d);
    const {value: api, calls} = controller(f.scope); await api.whenIdle();
    draft(api, f.book, 'Saved in flight'); click(api, f.book, 'save-note'); choose(api, f.book, 'cleanup-card'); draft(api, f.book, 'Unsaved draft');
    api.cleanup(); await new Promise(resolve => setImmediate(resolve));
    const again = controller(f.scope).value; await again.whenIdle();
    const transfer = await exported(again, f.book); assert(transfer.state.notes.some(note => note.text === 'Saved in flight')); assert(transfer.state.notes.some(note => note.text === 'Unsaved draft')); again.cleanup();
    const late = new DocumentDouble(), g = report(late, 'late', {key:'reader'}), raw = encodeReaderState(stateWith(g.context,[{type:'navigate',viewId:'detail',mode:'single',journeyId:'intro'}]));
    storage(late, [['reader',raw]]); const attached = controller(g.scope); attached.value.cleanup();
    await new Promise(resolve => setImmediate(resolve)); await new Promise(resolve => setImmediate(resolve));
    assert.equal(attached.calls.navigations.length, 0, 'Cleanup cancels asynchronous saved-place restoration');
  });
  await check("metadata disagreements, missing roots and duplicate target IDs fail locally without writes", async () => {
    for (const conflict of [{revision:'other'}, {key:'other'}, {limit:0}]) {
      const d = new DocumentDouble(), f = report(d, 'metadata', {key:'reader'}), store = storage(d);
      const second = notebook(f.scope, 'metadata', 'second-book', conflict), api = controller(f.scope).value;
      assert.match(status(f.book), /disagree/); assert.match(status(second), /disagree/); assert.equal(store.indexedDB.calls.length, 0); api.cleanup();
    }
    const d = new DocumentDouble(), f = report(d, 'duplicate'), other = append(d.body, 'div', {id:'duplicate-card'});
    const api = controller(f.scope).value; assert.match(status(f.book), /unique IDs/); api.cleanup(); other.remove();
    const missing = notebook(d.body, 'absent', 'missing-book'), root = controller(d.body).value; assert.match(status(missing), /containing report/); root.cleanup();
  });
  await check("an explicit sibling fragment and intervening focus do not misapply asynchronous restore", async () => {
    const d = new DocumentDouble(), a = report(d, 'explicit', {key:'a'}), b = report(d, 'sibling', {key:'b'});
    const raw = f => encodeReaderState(stateWith(f.context,[{type:'navigate',viewId:'detail',mode:'single',journeyId:'intro'}]));
    storage(d, [['a',raw(a)],['b',raw(b)]]); d.defaultView.location.hash='#explicit-start';
    const ca = controller(a.scope), cb = controller(b.scope); await Promise.all([ca.value.whenIdle(),cb.value.whenIdle()]);
    assert.equal(ca.calls.navigations.length,0); assert.equal(cb.calls.navigations.length,1); ca.value.cleanup(); cb.value.cleanup();
    const e = new DocumentDouble(), f = report(e,'focus',{key:'reader'}); storage(e,[['reader',raw(f)]]);
    const attached=controller(f.scope); query(f.book,'[data-av-notebook-note]').focus(); await attached.value.whenIdle();
    assert.equal(attached.calls.navigations.length,0); assert.equal(attached.value.restore(f.scope).viewId,'detail'); attached.value.cleanup();
  });
  await check("exhausted activity counters still permit lossless draft export", async () => {
    const d = new DocumentDouble(), f = report(d, 'exhausted', {key:'reader'});
    const state = {...emptyReaderState(f.context), droppedActivityCount:Number.MAX_SAFE_INTEGER-1, nextSequence:Number.MAX_SAFE_INTEGER};
    storage(d, [['reader',encodeReaderState(state)]]); const api = controller(f.scope).value; await api.whenIdle();
    draft(api, f.book, 'Keep this draft'); click(api, f.book, 'save-note'); assert.match(status(f.book), /capacity reached/);
    const transfer = await exported(api, f.book); assert.equal(transfer.state.notes[0].text, 'Keep this draft'); assert.equal(transfer.state.nextSequence, Number.MAX_SAFE_INTEGER); api.cleanup();
  });
  await check("direct section links and early navigation retain a replaced notebook", async () => {
    for(const directLink of [false,true]) {
      const d=new DocumentDouble(), first=report(d,'linked',{key:'reader'}), store=storage(d);
      const initial=controller(first.scope).value; await initial.whenIdle();
      click(initial,first.book,'start-reset'); click(initial,first.book,'confirm-reset'); await initial.whenIdle();
      choose(initial,first.book,'linked-card'); draft(initial,first.book,'Saved before opening the direct link'); click(initial,first.book,'save-note'); await initial.whenIdle(); initial.cleanup();
      const nextD=new DocumentDouble(), next=report(nextD,'linked',{key:'reader'}); storage(nextD,[],store.indexedDB); store.indexedDB.paused=true;
      let close, transfer;
      if(directLink) {
        nextD.defaultView.location.hash='#linked-detail'; close=enhanceVisuals(next.scope);
        store.indexedDB.resume(); await close.whenIdle();
        send(action(next.book,'export'),'click'); await close.whenIdle();
        const href=action(next.book,'download').getAttribute('href'); transfer=JSON.parse(decodeURIComponent(href.slice(href.indexOf(',')+1)));
      } else {
        const early=controller(next.scope).value; close=Object.assign(()=>early.cleanup(),{whenIdle:()=>early.whenIdle()});
        early.recordPlace(next.scope,{viewId:'detail',mode:'single',journeyId:null});
        store.indexedDB.resume(); await close.whenIdle(); transfer=await exported(early,next.book);
      }
      assert(!/incompatible|replaced/.test(status(next.book)), status(next.book));
      assert(transfer.state.notes.some(note=>note.text==='Saved before opening the direct link'));
      assert(saved(store,'reader').state.notes.some(note=>note.text==='Saved before opening the direct link'));
      assert.equal(transfer.state.viewId,'detail'); assert(action(next.book,'recover').hidden); close();
    }
  });
  await check("unseen notes survive early edits while observed stale epochs remain protected", async () => {
    const d=new DocumentDouble(), first=report(d,'early',{key:'reader'}), store=storage(d), a=controller(first.scope).value; await a.whenIdle();
    click(a,first.book,'start-reset');click(a,first.book,'confirm-reset');await a.whenIdle();
    choose(a,first.book,'early-card');draft(a,first.book,'Previously saved');click(a,first.book,'save-note');await a.whenIdle();
    const otherD=new DocumentDouble(), other=report(otherD,'early',{key:'reader'});storage(otherD,[],store.indexedDB);store.indexedDB.paused=true;
    const b=controller(other.scope).value; choose(b,other.book,'early-card');draft(b,other.book,'Written before loading');click(b,other.book,'save-note');
    store.indexedDB.resume();await b.whenIdle();
    const transfer=await exported(b,other.book);assert(transfer.noteVersions.some(note=>note.text==='Previously saved'));assert(transfer.noteVersions.some(note=>note.text==='Written before loading'));
    const resetD=new DocumentDouble(), resetView=report(resetD,'early',{key:'reader'});storage(resetD,[],store.indexedDB);const c=controller(resetView.scope).value;await c.whenIdle();
    click(c,resetView.book,'start-reset');click(c,resetView.book,'confirm-reset');await c.whenIdle();
    const epoch=saved(store,'reader').epoch; b.recordPlace(other.scope,{viewId:'extra',mode:'single',journeyId:null});await b.whenIdle();
    assert.equal(saved(store,'reader').epoch,epoch);assert.equal(saved(store,'reader').state.viewId,null);
    assert(/replaced|changed|protected/.test(status(other.book)),status(other.book));a.cleanup();b.cleanup();c.cleanup();
  });
  console.log(`notebook contracts passed: ${passed.length} behavior groups (DOM/transaction doubles; native browser unverified)`);
  for (const name of passed) console.log('- ' + name);
})().catch(error => { console.error(error); process.exitCode = 1; });
