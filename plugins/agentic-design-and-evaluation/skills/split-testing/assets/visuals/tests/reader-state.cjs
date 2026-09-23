// Pure behavior checks. No DOM, browser, clock, filesystem storage, or telemetry.
const assert = require("node:assert/strict");
const path = require("node:path");
const {
  READER_STATE_VERSION, DEFAULT_READER_ACTIVITY_LIMIT,
  emptyReaderState, decodeReaderState, encodeReaderState, updateReaderState,
  loadReaderState, emptyReaderNotebook, applyReaderDelta, mergeReaderNotebooks, encodeReaderNotebook, decodeReaderNotebook,
} = require(path.join(process.argv[2], "reader-state.js"));

const context = {
  reportId: "study / reader", revision: "revision 01",
  targetIds: ["alpha", "beta", "__proto__", "0", ""],
  viewIds: ["start", "details", "view-only"], journeyIds: ["first", "second"],
};
const at = "2026-09-17T12:30:00.000Z";
const earlier = "2026-09-16T09:15:00-07:00";
const update = (state, change, scope = context) => updateReaderState(state, { at, ...change }, scope);
const clone = state => JSON.parse(JSON.stringify(state));
const passed = [];
function check(name, body) { body(); passed.push(name); }
function frozen(value) {
  if (value && typeof value === "object") {
    for (const item of Object.values(value)) frozen(item);
    Object.freeze(value);
  }
  return value;
}
function storageFixture(entries = []) {
  const values = new Map(entries), calls = [];
  const storage = {
    getItem(key) { calls.push(["get", key]); return values.get(key) ?? null; },
    setItem(key, value) { calls.push(["set", key, value]); values.set(key, value); },
    removeItem(key) { calls.push(["remove", key]); values.delete(key); },
    clear() { assert.fail("Reader storage must not be cleared"); },
    key() { assert.fail("Reader storage must not be enumerated"); },
    get length() { assert.fail("Reader storage must not be enumerated"); },
  };
  return { values, calls, storage };
}

check("empty records and JSON equivalence", () => {
  assert.equal(READER_STATE_VERSION, 1);
  assert.equal(DEFAULT_READER_ACTIVITY_LIMIT, 128);
  const state = emptyReaderState(context);
  assert.deepEqual(state, {
    version: 1, reportId: context.reportId, revision: context.revision,
    viewId: null, mode: "single", journeyId: null, bookmarks: [], notes: [],
    activity: [], droppedActivityCount: 0, nextSequence: 1,
  });
  assert.deepEqual(decodeReaderState(encodeReaderState(state), context), state);
  assert.notEqual(emptyReaderState(context).notes, state.notes);
  const noTargets = { ...context, targetIds: [], viewIds: [], journeyIds: [] };
  assert.deepEqual(decodeReaderState(encodeReaderState(emptyReaderState(noTargets)), noTargets), emptyReaderState(noTargets));
});

check("opaque IDs retain their supplied values", () => {
  let state = emptyReaderState(context);
  for (const targetId of ["__proto__", "", "0"]) state = update(state, { type: "bookmark", targetId, enabled: true });
  state = update(state, { type: "note", targetId: "__proto__", text: "0" });
  assert.deepEqual(state.bookmarks, ["__proto__", "", "0"]);
  assert.equal(state.notes[0].targetId, "__proto__");
  assert.deepEqual(decodeReaderState(encodeReaderState(state), context), state);
  const sharedIdContext = { ...context, viewIds: ["alpha"], journeyIds: ["alpha"] };
  assert.equal(update(emptyReaderState(sharedIdContext), { type: "navigate", viewId: "alpha", mode: "single", journeyId: "alpha" }, sharedIdContext).journeyId, "alpha");
});

check("navigation retains destination separately from targets", () => {
  let state = update(emptyReaderState(context), { type: "navigate", viewId: "view-only", mode: "single", journeyId: "first" });
  assert.deepEqual(state.activity, [{ sequence: 1, at, action: "open-view", viewId: "view-only" }]);
  assert.equal(state.journeyId, "first");
  state = update(state, { type: "navigate", viewId: "details", mode: "all" });
  assert.equal(state.viewId, "details");
  assert.equal(state.mode, "all");
  assert.equal(state.journeyId, "first", "omission preserves the current journey");
  state = update(state, { type: "navigate", viewId: "details", mode: "single", journeyId: null });
  assert.equal(state.journeyId, null);
  state = update(state, { type: "navigate", viewId: "details", mode: "single" });
  assert.equal(state.activity.length, 4, "reopening is an action, without any understanding/completion inference");
  assert.deepEqual(decodeReaderState(encodeReaderState(state), context), state);
  assert.throws(() => update(state, { type: "activity", action: "inspect", targetId: "view-only" }), /not declared/);
});

check("bookmarks keep action order and idempotent changes do not invent events", () => {
  let state = update(emptyReaderState(context), { type: "bookmark", targetId: "beta", enabled: true });
  state = update(state, { type: "bookmark", targetId: "alpha", enabled: true });
  assert.deepEqual(state.bookmarks, ["beta", "alpha"]);
  const before = encodeReaderState(state);
  state = update(state, { type: "bookmark", targetId: "beta", enabled: true });
  state = update(state, { type: "bookmark", targetId: "0", enabled: false });
  assert.equal(encodeReaderState(state), before);
  state = update(state, { type: "bookmark", targetId: "beta", enabled: false });
  state = update(state, { type: "bookmark", targetId: "beta", enabled: true });
  assert.deepEqual(state.bookmarks, ["alpha", "beta"]);
  assert.deepEqual(state.activity.map(entry => entry.action), ["bookmark-added", "bookmark-added", "bookmark-removed", "bookmark-added"]);
});

check("notes preserve exact text, deletion, update order and event privacy", () => {
  const text = "  0\nnaïve e\u0301 • 日本語 🪶\t<script>text only</script>  ";
  let state = update(emptyReaderState(context), { type: "note", targetId: "beta", text });
  state = update(state, { type: "note", targetId: "alpha", text: "0" });
  assert.equal(state.notes[0].text, text);
  assert.equal(state.notes[1].text, "0");
  assert.deepEqual(state.notes.map(note => note.targetId), ["beta", "alpha"]);
  assert.equal(JSON.stringify(state.activity).includes(text), false);
  assert.ok(state.activity.every(entry => Object.keys(entry).every(key => ["sequence", "at", "action", "targetId"].includes(key))));
  state = update(state, { type: "note", targetId: "beta", text: " \t\n", at: earlier });
  assert.equal(state.notes[0].text, " \t\n", "whitespace is a saved note, not a deletion");
  assert.equal(state.notes[0].updatedAt, earlier, "caller timestamps are not rewritten or sorted");
  assert.deepEqual(state.notes.map(note => note.targetId), ["beta", "alpha"]);
  state = update(state, { type: "note", targetId: "beta", text: "" });
  assert.deepEqual(state.notes.map(note => note.targetId), ["alpha"]);
  assert.equal(state.activity.at(-1).action, "note-removed");
  const before = encodeReaderState(state);
  assert.equal(encodeReaderState(update(state, { type: "note", targetId: "beta", text: "" })), before);
  assert.deepEqual(decodeReaderState(encodeReaderState(state), context), state);
});

check("retention counts dropped entries and never reuses a sequence", () => {
  const scope = { ...context, activityLimit: 2 };
  let state = emptyReaderState(scope);
  for (let index = 1; index <= 6; index++) state = update(state, { type: "activity", action: `action-${index}`, at: index % 2 ? at : earlier }, scope);
  assert.deepEqual(state.activity.map(entry => entry.sequence), [5, 6]);
  assert.deepEqual(state.activity.map(entry => entry.at), [at, earlier]);
  assert.equal(state.droppedActivityCount, 4);
  assert.equal(state.nextSequence, 7);
  state = update(state, { type: "note", targetId: "alpha", text: "Retained outside history" }, scope);
  assert.deepEqual(state.activity.map(entry => entry.sequence), [6, 7]);
  assert.equal(state.droppedActivityCount, 5);
  assert.equal(state.nextSequence, 8);
  assert.equal(state.notes[0].text, "Retained outside history");
  assert.deepEqual(decodeReaderState(encodeReaderState(state), scope), state);
  assert.deepEqual(decodeReaderState(encodeReaderState(state), { ...context, activityLimit: 10 }), state, "increasing capacity cannot recreate previously dropped actions");
  const trimmed = decodeReaderState(encodeReaderState(state), { ...context, activityLimit: 1 });
  assert.equal(trimmed.activity.length, 1);
  assert.equal(trimmed.nextSequence, state.nextSequence);
  assert.equal(trimmed.droppedActivityCount, state.nextSequence - 2);
  assert.deepEqual(trimmed.notes, state.notes);
  assert.deepEqual(trimmed.bookmarks, state.bookmarks);
  let standard = emptyReaderState(context);
  for (let index = 0; index < 130; index++) standard = update(standard, { type: "activity", action: "inspect" });
  assert.equal(standard.activity.length, 128);
  assert.equal(standard.droppedActivityCount, 2);
  assert.equal(standard.nextSequence, 131);
});

check("zero retention disables history without erasing reader records", () => {
  const scope = { ...context, activityLimit: 0 };
  let state = update(emptyReaderState(scope), { type: "note", targetId: "alpha", text: "private reader note" }, scope);
  state = update(state, { type: "bookmark", targetId: "alpha", enabled: true }, scope);
  state = update(state, { type: "navigate", viewId: "start", mode: "single" }, scope);
  assert.deepEqual(state.activity, []);
  assert.equal(state.droppedActivityCount, 3);
  assert.equal(state.nextSequence, 4);
  assert.deepEqual(state.bookmarks, ["alpha"]);
  assert.equal(state.notes[0].text, "private reader note");
  assert.deepEqual(decodeReaderState(encodeReaderState(state), scope), state);
});

check("storage keys are isolated and loads never write or reset", () => {
  const state = update(emptyReaderState(context), { type: "note", targetId: "alpha", text: "Remember the conditions" });
  const fixture = storageFixture([["unrelated", "do not touch"], ["another-report", "other reader records"]]);
  const emptyResult = loadReaderState(fixture.storage, "reader/current", context);
  assert.equal(emptyResult.status, "empty");
  assert.deepEqual(emptyResult.state, emptyReaderState(context));
  assert.deepEqual(fixture.calls, [["get", "reader/current"]]);
  fixture.values.set("reader/current", encodeReaderState(state));
  assert.equal(fixture.values.get("unrelated"), "do not touch");
  assert.equal(fixture.values.get("another-report"), "other reader records");
  const before = [...fixture.values];
  const loaded = loadReaderState(fixture.storage, "reader/current", context);
  assert.equal(loaded.status, "loaded");
  assert.deepEqual(loaded.state, state);
  assert.deepEqual([...fixture.values], before);
  assert.deepEqual(fixture.calls.map(call => call.slice(0, 2)), [["get", "reader/current"], ["get", "reader/current"]]);
  fixture.values.set("", encodeReaderState(state));
  assert.equal(loadReaderState(fixture.storage, "", context).status, "loaded");
});

check("corrupt and incompatible storage retains exact recovery text", () => {
  for (const raw of ["", " { not json\n", '{"version":1,"notes":"do not discard"}']) {
    const fixture = storageFixture([["reader", raw]]);
    const result = loadReaderState(fixture.storage, "reader", context);
    assert.equal(result.status, "invalid");
    assert.equal(result.raw, raw);
    assert.equal("state" in result, false);
    assert.equal(fixture.values.get("reader"), raw);
    assert.deepEqual(fixture.calls, [["get", "reader"]]);
  }
  for (const changedIdentity of [{ reportId: "another report" }, { revision: "revision 02" }]) {
    const other = update(emptyReaderState({ ...context, ...changedIdentity }), { type: "note", targetId: "beta", text: "recovery needed" }, { ...context, ...changedIdentity });
    const raw = `\n${encodeReaderState(other)}  `;
    const fixture = storageFixture([["reader", raw]]);
    const result = loadReaderState(fixture.storage, "reader", context);
    assert.equal(result.status, "mismatch");
    assert.equal(result.raw, raw);
    assert.equal("state" in result, false);
    assert.deepEqual(fixture.calls, [["get", "reader"]]);
    assert.equal(fixture.values.get("reader"), raw);
    assert.throws(() => decodeReaderState(raw, context), /different report or revision/);
  }
  const foreign = { ...emptyReaderState(context), reportId: "elsewhere", bookmarks: ["foreign-target"] };
  const fixture = storageFixture([["reader", JSON.stringify(foreign)]]);
  assert.equal(loadReaderState(fixture.storage, "reader", context).status, "mismatch", "other reports may have their own valid target IDs");
});

check("storage failures are honest, concise and leave export available", () => {
  const state = emptyReaderState(context);
  assert.equal(loadReaderState(null, "reader", context).status, "unavailable");
  const fixture = storageFixture([["reader", "old data"]]);
  fixture.storage.getItem = () => { throw new Error("private diagnostic detail"); };
  const unreadable = loadReaderState(fixture.storage, "reader", context);
  assert.equal(unreadable.status, "unavailable");
  assert.equal(unreadable.message.includes("private diagnostic detail"), false);
  assert.equal(fixture.values.get("reader"), "old data");
  assert.deepEqual(decodeReaderState(encodeReaderState(state), context), state);
  const invalidState = { ...state, mode: "compact" };
  const writes = storageFixture();
  assert.throws(() => encodeReaderState(invalidState));
  assert.deepEqual(writes.calls, [], "invalid state is not partially persisted");
  writes.storage.getItem = () => 7;
  assert.equal(loadReaderState(writes.storage, "reader", context).status, "unavailable");
});

check("unknown references are rejected without dropping saved records", () => {
  const base = emptyReaderState(context);
  for (const partial of [
    { viewId: "unknown" }, { journeyId: "unknown" }, { bookmarks: ["unknown"] },
    { notes: [{ targetId: "unknown", text: "keep this", updatedAt: at }] },
    { activity: [{ sequence: 1, at, action: "inspect", targetId: "unknown" }], nextSequence: 2 },
    { activity: [{ sequence: 1, at, action: "open-view", viewId: "unknown" }], nextSequence: 2 },
  ]) {
    const raw = JSON.stringify({ ...base, ...partial });
    const fixture = storageFixture([["reader", raw]]);
    const result = loadReaderState(fixture.storage, "reader", context);
    assert.equal(result.status, "invalid");
    assert.match(result.message, /not declared/);
    assert.equal(result.raw, raw);
    assert.equal(fixture.values.get("reader"), raw);
  }
  for (const change of [
    { type: "navigate", viewId: "unknown", mode: "single" },
    { type: "navigate", viewId: "start", mode: "single", journeyId: "unknown" },
    { type: "bookmark", targetId: "unknown", enabled: false },
    { type: "note", targetId: "unknown", text: "" },
    { type: "activity", action: "inspect", targetId: "unknown" },
  ]) assert.throws(() => update(base, change), /not declared/);
});

check("schemas, enums and duplicate IDs fail explicitly", () => {
  const base = emptyReaderState(context);
  for (const field of ["targetIds", "viewIds", "journeyIds"]) assert.throws(() => emptyReaderState({ ...context, [field]: ["x", "x"] }), /duplicate/);
  for (const partial of [{ reportId: "" }, { revision: "" }, { targetIds: [0] }, { viewIds: null }, { journeyIds: "first" }]) assert.throws(() => emptyReaderState({ ...context, ...partial }));
  for (const value of [null, [], 1, "state", { ...base, version: 2 }, { ...base, mode: "compact" }, { ...base, findings: [] }, { ...base, bookmarks: ["alpha", "alpha"] }, { ...base, notes: [{ targetId: "alpha", text: "", updatedAt: at }] }]) assert.throws(() => decodeReaderState(JSON.stringify(value), context));
  const missing = clone(base); delete missing.mode;
  assert.throws(() => decodeReaderState(JSON.stringify(missing), context), /missing mode/);
  const note = { targetId: "alpha", text: "0", updatedAt: at };
  assert.throws(() => decodeReaderState(JSON.stringify({ ...base, notes: [note, note] }), context), /duplicate/);
  assert.throws(() => decodeReaderState(JSON.stringify({ ...base, notes: [{ ...note, importance: 1 }] }), context), /unsupported field/);
  assert.throws(() => update(base, { type: "rank", action: "inspect" }), /navigate, bookmark, note or activity/);
  assert.throws(() => update(base, { type: "navigate", viewId: "start", mode: "compact" }), /single or all/);
  assert.throws(() => update(base, { type: "bookmark", targetId: "alpha", enabled: 1 }), /true or false/);
  assert.throws(() => update(base, { type: "note", targetId: "alpha", text: 0 }), /string/);
  assert.throws(() => update(base, { type: "activity", action: "" }), /nonempty string/);
  assert.throws(() => update(base, { type: "activity", action: "inspect", text: "unrecognized payload" }), /unsupported field/);
});

check("malformed counters and history bounds are never repaired silently", () => {
  const base = emptyReaderState(context);
  for (const invalid of [-1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, "2"]) {
    assert.throws(() => emptyReaderState({ ...context, activityLimit: invalid }), /safe integer/);
    assert.throws(() => encodeReaderState({ ...base, droppedActivityCount: invalid }), /safe integer/);
  }
  for (const invalid of [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) assert.throws(() => encodeReaderState({ ...base, nextSequence: invalid }), /safe integer/);
  for (const partial of [
    { droppedActivityCount: 1 }, { nextSequence: 2 },
    { activity: [{ sequence: 2, at, action: "inspect" }], nextSequence: 2 },
    { activity: [{ sequence: 1, at, action: "inspect" }, { sequence: 1, at, action: "inspect" }], nextSequence: 3 },
    { activity: [{ sequence: 0, at, action: "inspect" }], nextSequence: 2 },
  ]) assert.throws(() => decodeReaderState(JSON.stringify({ ...base, ...partial }), context));
  const exhausted = { ...base, droppedActivityCount: Number.MAX_SAFE_INTEGER - 1, nextSequence: Number.MAX_SAFE_INTEGER };
  assert.deepEqual(decodeReaderState(encodeReaderState(exhausted), context), exhausted);
  assert.throws(() => update(exhausted, { type: "activity", action: "inspect" }), /capacity reached/);
  assert.equal(exhausted.nextSequence, Number.MAX_SAFE_INTEGER);
});

check("timestamps are explicit, valid and preserved without a system clock", () => {
  const base = emptyReaderState(context);
  for (const invalid of [undefined, "", "2026-09-17", "2026-09-17T12:30:00", "2026-02-29T00:00:00Z", "1900-02-29T00:00:00Z", "2026-04-31T00:00:00Z", "2026-13-01T00:00:00Z", "2026-00-01T00:00:00Z", "2026-01-00T00:00:00Z", "2026-01-01T24:00:00Z", "2026-01-01T00:60:00Z", "2026-01-01T00:00:60Z", "2026-01-01T00:00:00+24:00", "2026-01-01T00:00:00-07:60"])
    assert.throws(() => updateReaderState(base, { type: "activity", action: "inspect", at: invalid }, context));
  for (const valid of ["2000-02-29T00:00:00Z", "2024-02-29T12:13:14.123456789+05:30", "0000-02-29T23:59:59-07:00"]) {
    const state = update(base, { type: "activity", action: "inspect", at: valid });
    assert.equal(state.activity[0].at, valid);
    assert.deepEqual(decodeReaderState(encodeReaderState(state), context), state);
  }
  const originalClock = Date.now;
  try {
    Date.now = () => assert.fail("A pure transition must not read the environment clock");
    assert.equal(update(base, { type: "activity", action: "inspect" }).activity[0].at, at);
  } finally { Date.now = originalClock; }
});

check("unsupported object behavior cannot execute during encode/update", () => {
  const base = emptyReaderState(context);
  let executions = 0;
  const getterState = { ...base };
  Object.defineProperty(getterState, "notes", { enumerable: true, get() { executions++; return []; } });
  assert.throws(() => encodeReaderState(getterState), /data properties/);
  assert.throws(() => update(getterState, { type: "activity", action: "inspect" }), /data properties/);
  const withSerializer = { ...base, toJSON() { executions++; return base; } };
  assert.throws(() => encodeReaderState(withSerializer), /unsupported field/);
  assert.equal(executions, 0);
  const inherited = Object.assign(Object.create({ inheritedMetadata: true }), base);
  assert.throws(() => encodeReaderState(inherited), /plain object/);
  assert.throws(() => decodeReaderState('{"__proto__":{"polluted":true}}', context), /unsupported field/);
  assert.equal({}.polluted, undefined);
  const sparse = new Array(1);
  assert.throws(() => encodeReaderState({ ...base, bookmarks: sparse }), /dense array/);
  const decorated = []; decorated.extra = "metadata";
  assert.throws(() => encodeReaderState({ ...base, notes: decorated }), /dense array/);
  class UnrecognizedArray extends Array {}
  assert.throws(() => encodeReaderState({ ...base, activity: new UnrecognizedArray() }), /plain array/);
  const getters = ["alpha"];
  Object.defineProperty(getters, "0", { enumerable: true, get() { executions++; return "alpha"; } });
  assert.throws(() => encodeReaderState({ ...base, bookmarks: getters }), /data entries/);
  assert.equal(executions, 0);
});

check("independent actions and harmless representation reordering preserve their meaning", () => {
  let state = update(emptyReaderState(context), { type: "note", targetId: "alpha", text: " 0 " });
  state = update(state, { type: "bookmark", targetId: "beta", enabled: true });
  state = update(state, { type: "bookmark", targetId: "alpha", enabled: true });
  const reorderedContext = { ...context, targetIds: [...context.targetIds].reverse(), viewIds: [...context.viewIds].reverse(), journeyIds: [...context.journeyIds].reverse() };
  const reorderedProperties = Object.fromEntries(Object.entries(state).reverse());
  assert.deepEqual(decodeReaderState(JSON.stringify(reorderedProperties), reorderedContext), state);
  assert.notDeepEqual(update(state, { type: "note", targetId: "alpha", text: "0" }).notes, state.notes);
  let otherOrder = update(emptyReaderState(context), { type: "bookmark", targetId: "alpha", enabled: true });
  otherOrder = update(otherOrder, { type: "bookmark", targetId: "beta", enabled: true });
  assert.notDeepEqual(otherOrder.bookmarks, state.bookmarks, "bookmark action order belongs to the reader");
  const reversedHistory = { ...state, activity: [...state.activity].reverse() };
  assert.throws(() => decodeReaderState(JSON.stringify(reversedHistory), context), /action order/);
  const noteAction = { type: "note", targetId: "alpha", text: "Retain exact wording" };
  const bookmarkAction = { type: "bookmark", targetId: "beta", enabled: true };
  const noteThenBookmark = update(update(emptyReaderState(context), noteAction), bookmarkAction);
  const bookmarkThenNote = update(update(emptyReaderState(context), bookmarkAction), noteAction);
  assert.deepEqual(noteThenBookmark.notes, bookmarkThenNote.notes);
  assert.deepEqual(noteThenBookmark.bookmarks, bookmarkThenNote.bookmarks);
  assert.notDeepEqual(noteThenBookmark.activity, bookmarkThenNote.activity, "independent changes can commute while their observed action chronology remains distinct");
});

check("earlier snapshots and caller inputs remain immutable", () => {
  const scope = frozen(clone(context));
  let first = update(emptyReaderState(scope), { type: "note", targetId: "alpha", text: "First note" }, scope);
  first = update(first, { type: "bookmark", targetId: "beta", enabled: true }, scope);
  const before = encodeReaderState(first);
  frozen(first);
  const change = frozen({ type: "note", targetId: "alpha", text: "Second note", at: earlier });
  const second = updateReaderState(first, change, scope);
  assert.equal(encodeReaderState(first), before);
  assert.equal(second.notes[0].text, "Second note");
  second.activity[0].action = "caller mutation";
  second.bookmarks.push("alpha");
  assert.equal(first.activity[0].action, "note-saved");
  assert.deepEqual(first.bookmarks, ["beta"]);
  const same = update(first, { type: "bookmark", targetId: "beta", enabled: true }, scope);
  same.notes[0].text = "mutated fresh result";
  assert.equal(first.notes[0].text, "First note");
  assert.throws(() => update(first, { type: "navigate", viewId: "not present", mode: "single" }, scope));
  assert.equal(encodeReaderState(first), before);
  assert.deepEqual(change, { type: "note", targetId: "alpha", text: "Second note", at: earlier });
  assert.deepEqual(scope, context);
});

check("review merges do not resurrect superseded annotation versions", () => {
  const scope = { ...context, targetIds: ["alpha"] };
  const anchor = { kind: "section", target: { reportId: scope.reportId, revision: scope.revision, id: "alpha", label: "Alpha", path: [], fingerprint: "sha256:test", excerpt: "Original evidence" } };
  const annotation = (book, id, text, observedIds = [], draft = false, baseIds, supportingVersions) => applyReaderDelta(book, {
    epoch: book.epoch, id: "delta-" + id,
    change: { type: "annotation", version: { id, annotationId: "annotation-1", anchor, text, at, draft, ...(baseIds ? { baseIds } : {}) }, observedIds, ...(supportingVersions ? { supportingVersions } : {}) },
  }, scope);
  const original = annotation(emptyReaderNotebook(scope), "v1", "Original note");
  const revised = annotation(original, "v2", "Revised note", ["v1"]);
  assert.deepEqual(revised.review.versions.map(version => version.id), ["v2"]);
  assert.deepEqual(revised.review.versions[0].baseIds, ["v1"], "A completed edit retains the version it explicitly replaced");
  assert.deepEqual(mergeReaderNotebooks(original, revised, scope).review.versions.map(version => version.id), ["v2"], "Merging an older snapshot cannot manufacture a conflict");

  const competing = annotation(original, "v3", "Concurrent note", ["v1"]);
  assert.deepEqual(mergeReaderNotebooks(revised, competing, scope).review.versions.map(version => version.id), ["v2", "v3"], "Independent descendants remain competing versions");

  const draft = annotation(original, "draft-1", "Work in progress", ["v1"], true, ["v1"]);
  assert.deepEqual(mergeReaderNotebooks(original, draft, scope).review.versions.map(version => version.id), ["v1", "draft-1"], "A draft keeps its saved base available beside it");

  const directDraft = annotation(original, "direct-draft", "Direct draft", ["v1"], true, ["v1"]);
  const directCompleted = annotation(directDraft, "direct-b", "Direct completed sibling", ["v1"]);
  assert.deepEqual(directCompleted.review.versions.map(version => version.id), ["direct-draft", "direct-b"]);
  assert.deepEqual(directCompleted.review.supportingVersions?.map(version => version.id), ["v1"], "Direct completed edits retain a live draft's exact saved base as supporting context");
  assert.deepEqual(directCompleted.review.supportingVersions?.[0], original.review.versions[0], "Supporting context preserves the exact saved annotation version");

  const mixed = mergeReaderNotebooks(revised, annotation(original, "draft-2", "Concurrent draft", ["v1"], true, ["v1"]), scope);
  assert.deepEqual(mixed.review.versions.map(version => version.id), ["v2", "draft-2"], "A completed sibling and live draft remain active without resurrecting their common base");
  assert.deepEqual(mixed.review.supportingVersions?.map(version => version.id), ["v1"], "The common saved base is retained once as supporting draft context");
  const mixedRoundTrip = decodeReaderNotebook(encodeReaderNotebook(mixed, scope), scope);
  assert.deepEqual(mixedRoundTrip.review.supportingVersions, mixed.review.supportingVersions, "Lossless backup preserves supporting draft context");
  const originalVersion=original.review.versions[0];
  const staleDraft=annotation(revised,"stale-draft","Draft saved after B",["v1"],true,["v1"],[originalVersion]);
  assert.deepEqual(staleDraft.review.versions.map(version=>version.id),["v2","stale-draft"],"A stale draft delta arriving after B keeps unseen B active");
  assert.deepEqual(staleDraft.review.supportingVersions?.map(version=>version.id),["v1"],"A stale draft delta carries the exact lost saved base into supporting context");
  assert.deepEqual(staleDraft.review.supportingVersions?.[0],originalVersion);
  const repeatedDraft=annotation(staleDraft,"stale-draft-2","Draft saved again",["v1","stale-draft"],true,["v1"],[originalVersion]);
  assert.deepEqual(repeatedDraft.review.versions.map(version=>version.id),["v2","stale-draft-2"]);
  assert.deepEqual(repeatedDraft.review.supportingVersions?.map(version=>version.id),["v1"],"Repeated draft saves retain one supporting copy of A");
  const finishedStale=annotation(repeatedDraft,"v5","Finished stale draft",["v1","stale-draft-2"],false,undefined,[originalVersion]);
  assert.deepEqual(finishedStale.review.versions.map(version=>version.id),["v2","v5"],"Finishing a stale draft keeps unseen B as a true competitor");
  assert.equal(finishedStale.review.supportingVersions,undefined);
  assert.throws(()=>annotation(staleDraft,"bad-support","Bad support",["v1","stale-draft"],true,["v1"],[{...originalVersion,text:"Conflicting A"}]),/Supporting annotation identity conflicts/);
  assert.throws(()=>annotation(revised,"unrelated-support","Unrelated support",["v1","other"],true,["v1"],[{...originalVersion,id:"other",annotationId:"other-annotation"}]),/referenced saved version of this annotation/);
  const validDraftBranch=annotation(original,"draft-valid","Valid same-annotation draft",["v1"],true,["v1"]);
  const crossGroupDraft={id:"draft-cross",annotationId:"other-annotation",anchor,text:"Malformed cross-group draft",at,draft:true,baseIds:["v1"]};
  const adversarial=mergeReaderNotebooks(revised,{...validDraftBranch,review:{...validDraftBranch.review,versions:[...validDraftBranch.review.versions,crossGroupDraft]}},scope);
  assert.deepEqual(adversarial.review.supportingVersions?.map(version=>version.id),["v1"],"A malformed cross-annotation reference cannot overwrite a valid draft's supporting base");
  const continued = annotation(mixed, "draft-3", "Continued concurrent draft", ["v1", "draft-2"], true, ["v1"]);
  assert.deepEqual(continued.review.supportingVersions?.map(version => version.id), ["v1"], "Successive draft saves reuse one retained supporting version");
  const finished = annotation(mixed, "v4", "Finished concurrent draft", ["v1", "draft-2"]);
  assert.deepEqual(finished.review.versions.map(version => version.id), ["v2", "v4"], "Finishing a draft retains an unseen completed sibling as a true conflict");
  assert.equal(finished.review.supportingVersions, undefined, "Draft-only support is removed once no live draft needs it");

  const blank = emptyReaderNotebook(scope);
  const cyclicVersion = (id, baseId, text) => ({ id, annotationId: "cyclic", anchor, text, at, draft: false, baseIds: [baseId] });
  const cycleLeft = { ...blank, review: { versions: [cyclicVersion("cycle-a", "cycle-b", "A"), cyclicVersion("cycle-old", "missing", "Older retained context")], bookmarks: [] } };
  const cycleRight = { ...blank, review: { versions: [cyclicVersion("cycle-b", "cycle-a", "B")], bookmarks: [] } };
  assert.deepEqual(mergeReaderNotebooks(cycleLeft, cycleRight, scope).review.versions.map(version => version.id), ["cycle-a", "cycle-old", "cycle-b"], "Malformed cyclic ancestry conservatively retains that annotation's competing records");

  const deep = Array.from({length:2000},(_,index)=>({
    id:"deep-"+index,annotationId:"deep",anchor,text:"Version "+index,at,draft:false,
    ...(index ? {baseIds:["deep-"+(index-1)]} : {}),
  }));
  const deepHistory = { ...blank, review: { versions: deep, bookmarks: [] } };
  assert.deepEqual(mergeReaderNotebooks(deepHistory, blank, scope).review.versions.map(version => version.id), ["deep-1999"], "Long acyclic ancestry is reduced iteratively without retaining superseded history");
});

console.log(`reader-state contracts passed: ${passed.length} behavior groups`);
for (const name of passed) console.log(`- ${name}`);
