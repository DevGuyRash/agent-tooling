import { exactJson } from './exact-json';
import { readerTimestamp } from "./reader-values";
import { ReviewRecords, ReviewChange, emptyReviewRecords, validateReview, applyReview } from "./review-state";
/** Optional reader records. These describe reader actions, never analytical findings. */
export const READER_STATE_VERSION = 1;
export const DEFAULT_READER_ACTIVITY_LIMIT = 128;

export type ReaderMode = "single" | "all";

export interface ReaderContext {
  readonly reportId: string;
  readonly revision: string;
  readonly targetIds: readonly string[];
  readonly viewIds: readonly string[];
  readonly journeyIds: readonly string[];
  readonly activityLimit?: number;
}

export interface ReaderNote {
  readonly targetId: string;
  readonly text: string;
  readonly updatedAt: string;
}

export interface ReaderActivity {
  readonly sequence: number;
  readonly at: string;
  readonly action: string;
  readonly targetId?: string;
  readonly viewId?: string;
}

export interface ReaderState {
  readonly version: typeof READER_STATE_VERSION;
  readonly reportId: string;
  readonly revision: string;
  readonly viewId: string | null;
  readonly mode: ReaderMode;
  readonly journeyId: string | null;
  readonly bookmarks: readonly string[];
  readonly notes: readonly ReaderNote[];
  readonly activity: readonly ReaderActivity[];
  readonly droppedActivityCount: number;
  readonly nextSequence: number;
}

export type ReaderChange =
  | { readonly type: "navigate"; readonly viewId: string; readonly mode: ReaderMode; readonly journeyId?: string | null; readonly at: string }
  | { readonly type: "bookmark"; readonly targetId: string; readonly enabled: boolean; readonly at: string }
  | { readonly type: "note"; readonly targetId: string; readonly text: string; readonly at: string }
  | { readonly type: "activity"; readonly action: string; readonly targetId?: string; readonly at: string };

export interface ReaderStorage {
  getItem(key: string): string | null;
}

export type ReaderLoadResult =
  | { readonly status: "empty" | "loaded"; readonly state: ReaderState }
  | { readonly status: "unavailable"; readonly message: string }
  | { readonly status: "invalid" | "mismatch"; readonly raw: string; readonly message: string };

class ReaderDataError extends Error {
  constructor(readonly kind: "invalid" | "mismatch", message: string) {
    super(message);
    this.name = "ReaderDataError";
  }
}

function invalid(message: string): never { throw new ReaderDataError("invalid", message); }

/** Inspect only own data properties; imported objects cannot supply getters or toJSON. */
function record(value: unknown, label: string, required: readonly string[], optional: readonly string[] = []): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) invalid(`${label} must be a plain object.`);
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) invalid(`${label} must be a plain object.`);
  const output: Record<string, unknown> = Object.create(null);
  const allowed = new Set([...required, ...optional]);
  for (const key of Reflect.ownKeys(value)) {
    if (typeof key !== "string" || !allowed.has(key)) invalid(`${label} has an unsupported field.`);
    const property = Object.getOwnPropertyDescriptor(value, key)!;
    if (!("value" in property) || !property.enumerable) invalid(`${label} must contain only enumerable data properties.`);
    output[key] = property.value;
  }
  for (const key of required) if (!Object.prototype.hasOwnProperty.call(output, key)) invalid(`${label} is missing ${key}.`);
  return output;
}

function array(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) invalid(`${label} must be a plain array.`);
  const length = Object.getOwnPropertyDescriptor(value, "length")!.value as number;
  if (Reflect.ownKeys(value).length !== length + 1) invalid(`${label} must be a dense array without extra fields.`);
  const output: unknown[] = [];
  for (let index = 0; index < length; index++) {
    const property = Object.getOwnPropertyDescriptor(value, String(index));
    if (!property || !("value" in property) || !property.enumerable) invalid(`${label} must contain only enumerable data entries.`);
    output.push(property.value);
  }
  return output;
}

function string(value: unknown, label: string, nonempty = false): string {
  if (typeof value !== "string" || (nonempty && value.length === 0)) invalid(`${label} must be ${nonempty ? "a nonempty string" : "a string"}.`);
  return value;
}

function counter(value: unknown, label: string, minimum = 0): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) invalid(`${label} must be a safe integer of at least ${minimum}.`);
  return value;
}

function mode(value: unknown): ReaderMode {
  if (value !== "single" && value !== "all") invalid("mode must be single or all.");
  return value;
}

/** Require an unambiguous ISO date-time; retain the caller's offset and precision. */
function timestamp(value: unknown, label: string): string { try { return readerTimestamp(value, label); } catch(error) { invalid(error instanceof Error ? error.message : 'Invalid timestamp.'); } }

function uniqueIds(value: unknown, label: string): string[] {
  const values = array(value, label).map(item => string(item, `${label} entry`));
  if (new Set(values).size !== values.length) invalid(`${label} contains duplicate IDs.`);
  return values;
}

interface Context {
  reportId: string;
  revision: string;
  targetIds: Set<string>;
  viewIds: Set<string>;
  journeyIds: Set<string>;
  activityLimit: number;
}

function contextOf(source: ReaderContext): Context {
  const item = record(source, "Reader context", ["reportId", "revision", "targetIds", "viewIds", "journeyIds"], ["activityLimit"]);
  return {
    reportId: string(item.reportId, "reportId", true),
    revision: string(item.revision, "revision", true),
    targetIds: new Set(uniqueIds(item.targetIds, "targetIds")),
    viewIds: new Set(uniqueIds(item.viewIds, "viewIds")),
    journeyIds: new Set(uniqueIds(item.journeyIds, "journeyIds")),
    activityLimit: item.activityLimit === undefined ? DEFAULT_READER_ACTIVITY_LIMIT : counter(item.activityLimit, "activityLimit"),
  };
}

function reference(value: string, ids: ReadonlySet<string>, label: string): void {
  if (!ids.has(value)) invalid(`${label} is not declared in the reader context.`);
}

/** Validate into a fresh, schema-limited snapshot before serialization or mutation. */
function stateOf(source: unknown, context?: Context): ReaderState {
  const item = record(source, "Reader state", ["version", "reportId", "revision", "viewId", "mode", "journeyId", "bookmarks", "notes", "activity", "droppedActivityCount", "nextSequence"]);
  if (item.version !== READER_STATE_VERSION) invalid(`Reader state version must be ${READER_STATE_VERSION}.`);
  const reportId = string(item.reportId, "reportId", true), revision = string(item.revision, "revision", true);
  const viewId = item.viewId === null ? null : string(item.viewId, "viewId");
  const journeyId = item.journeyId === null ? null : string(item.journeyId, "journeyId");
  const bookmarks = uniqueIds(item.bookmarks, "bookmarks");
  const notes: ReaderNote[] = array(item.notes, "notes").map(value => {
    const note = record(value, "Reader note", ["targetId", "text", "updatedAt"]);
    return { targetId: string(note.targetId, "Note targetId"), text: string(note.text, "Note text", true), updatedAt: timestamp(note.updatedAt, "Note updatedAt") };
  });
  if (new Set(notes.map(note => note.targetId)).size !== notes.length) invalid("notes contains duplicate target IDs.");
  const activity: ReaderActivity[] = array(item.activity, "activity").map(value => {
    const entry = record(value, "Reader activity", ["sequence", "at", "action"], ["targetId", "viewId"]);
    return {
      sequence: counter(entry.sequence, "Activity sequence", 1), at: timestamp(entry.at, "Activity at"), action: string(entry.action, "Activity action", true),
      ...(Object.prototype.hasOwnProperty.call(entry, "targetId") ? { targetId: string(entry.targetId, "Activity targetId") } : {}),
      ...(Object.prototype.hasOwnProperty.call(entry, "viewId") ? { viewId: string(entry.viewId, "Activity viewId") } : {}),
    };
  });
  const droppedActivityCount = counter(item.droppedActivityCount, "droppedActivityCount");
  const nextSequence = counter(item.nextSequence, "nextSequence", 1);
  if (droppedActivityCount > Number.MAX_SAFE_INTEGER - activity.length || nextSequence - 1 !== droppedActivityCount + activity.length) invalid("Activity counters do not match the retained history.");
  if (activity.some((entry, index) => entry.sequence !== droppedActivityCount + index + 1)) invalid("Activity sequences must preserve contiguous action order after dropped entries.");
  const state: ReaderState = { version: READER_STATE_VERSION, reportId, revision, viewId, mode: mode(item.mode), journeyId, bookmarks, notes, activity, droppedActivityCount, nextSequence };
  if (context) {
    if (reportId !== context.reportId || revision !== context.revision) throw new ReaderDataError("mismatch", "Saved reader records belong to a different report or revision.");
    if (viewId !== null) reference(viewId, context.viewIds, "viewId");
    if (journeyId !== null) reference(journeyId, context.journeyIds, "journeyId");
    for (const id of bookmarks) reference(id, context.targetIds, "Bookmark targetId");
    for (const note of notes) reference(note.targetId, context.targetIds, "Note targetId");
    for (const entry of activity) {
      if (entry.targetId !== undefined) reference(entry.targetId, context.targetIds, "Activity targetId");
      if (entry.viewId !== undefined) reference(entry.viewId, context.viewIds, "Activity viewId");
    }
  }
  const excess = context ? Math.max(0, state.activity.length - context.activityLimit) : 0;
  return excess ? { ...state, activity: state.activity.slice(excess), droppedActivityCount: state.droppedActivityCount + excess } : state;
}

function empty(context: Context): ReaderState {
  return { version: READER_STATE_VERSION, reportId: context.reportId, revision: context.revision, viewId: null, mode: "single", journeyId: null, bookmarks: [], notes: [], activity: [], droppedActivityCount: 0, nextSequence: 1 };
}

export function emptyReaderState(context: ReaderContext): ReaderState { return empty(contextOf(context)); }

function decode(text: string, context: Context): ReaderState {
  if (typeof text !== "string") invalid("Reader data must be JSON text.");
  let value: unknown;
  try { value = JSON.parse(text); }
  catch { invalid("Reader data is not valid JSON."); }
  return stateOf(value, context);
}

/** Invalid or incompatible imports throw without changing or discarding the source text. */
export function decodeReaderState(text: string, context: ReaderContext): ReaderState { return decode(text, contextOf(context)); }

/** Schema validation here needs no browser; reference validation happens with context on load/update. */
export function encodeReaderState(state: ReaderState): string { return exactJson(stateOf(state)); }

function appendActivity(state: ReaderState, entry: Omit<ReaderActivity, "sequence">, limit: number): ReaderState {
  if (state.nextSequence === Number.MAX_SAFE_INTEGER) invalid("Activity sequence capacity reached; start a new reader notebook.");
  const history = [...state.activity, { sequence: state.nextSequence, ...entry }];
  const dropped = Math.max(0, history.length - limit);
  return { ...state, activity: history.slice(dropped), droppedActivityCount: state.droppedActivityCount + dropped, nextSequence: state.nextSequence + 1 };
}

/** Opening is logged as opening; timestamps never reorder supplied actions or notes. */
export function updateReaderState(source: ReaderState, change: ReaderChange, context: ReaderContext): ReaderState {
  const scope = contextOf(context);
  const state = stateOf(source, scope);
  const item = record(change, "Reader change", ["type", "at"], ["viewId", "mode", "journeyId", "targetId", "enabled", "text", "action"]);
  const at = timestamp(item.at, "Change at");
  switch (item.type) {
    case "navigate": {
      const navigation = record(item, "Navigation change", ["type", "at", "viewId", "mode"], ["journeyId"]);
      const viewId = string(navigation.viewId, "viewId");
      reference(viewId, scope.viewIds, "viewId");
      const journeyId = navigation.journeyId === undefined ? state.journeyId : navigation.journeyId === null ? null : string(navigation.journeyId, "journeyId");
      if (journeyId !== null) reference(journeyId, scope.journeyIds, "journeyId");
      return appendActivity({ ...state, viewId, mode: mode(navigation.mode), journeyId }, { at, action: "open-view", viewId }, scope.activityLimit);
    }
    case "bookmark": {
      const bookmark = record(item, "Bookmark change", ["type", "at", "targetId", "enabled"]);
      const targetId = string(bookmark.targetId, "targetId");
      reference(targetId, scope.targetIds, "targetId");
      if (typeof bookmark.enabled !== "boolean") invalid("Bookmark enabled must be true or false.");
      if (state.bookmarks.includes(targetId) === bookmark.enabled) return state;
      const bookmarks = bookmark.enabled ? [...state.bookmarks, targetId] : state.bookmarks.filter(id => id !== targetId);
      return appendActivity({ ...state, bookmarks }, { at, action: bookmark.enabled ? "bookmark-added" : "bookmark-removed", targetId }, scope.activityLimit);
    }
    case "note": {
      const note = record(item, "Note change", ["type", "at", "targetId", "text"]);
      const targetId = string(note.targetId, "targetId"), text = string(note.text, "Note text");
      reference(targetId, scope.targetIds, "targetId");
      const index = state.notes.findIndex(previous => previous.targetId === targetId);
      if (text === "" && index < 0) return state;
      const notes = [...state.notes];
      if (text === "") notes.splice(index, 1);
      else if (index < 0) notes.push({ targetId, text, updatedAt: at });
      else notes[index] = { targetId, text, updatedAt: at };
      return appendActivity({ ...state, notes }, { at, action: text === "" ? "note-removed" : "note-saved", targetId }, scope.activityLimit);
    }
    case "activity": {
      const activity = record(item, "Activity change", ["type", "at", "action"], ["targetId"]);
      const action = string(activity.action, "Activity action", true);
      const targetId = activity.targetId === undefined ? undefined : string(activity.targetId, "Activity targetId");
      if (targetId !== undefined) reference(targetId, scope.targetIds, "Activity targetId");
      return appendActivity(state, { at, action, ...(targetId === undefined ? {} : { targetId }) }, scope.activityLimit);
    }
    default: invalid("Reader change type must be navigate, bookmark, note or activity.");
  }
}

/** Read only the supplied key. Failed/incompatible loads never initialize or repair storage. */
export function loadReaderState(storage: ReaderStorage | null, key: string, context: ReaderContext): ReaderLoadResult {
  const scope = contextOf(context);
  string(key, "Storage key");
  if (storage === null) return { status: "unavailable", message: "Reader storage is unavailable." };
  let raw: string | null;
  try { raw = storage.getItem(key); }
  catch { return { status: "unavailable", message: "Reader storage could not be read." }; }
  if (raw === null) return { status: "empty", state: empty(scope) };
  if (typeof raw !== "string") return { status: "unavailable", message: "Reader storage did not return text." };
  try { return { status: "loaded", state: decode(raw, scope) }; }
  catch (error) {
    return { status: error instanceof ReaderDataError ? error.kind : "invalid", raw, message: error instanceof ReaderDataError ? error.message : "Reader data could not be loaded." };
  }
}

/** A lossless notebook transfer preserves concurrent versions and legacy source bytes. */
export interface ReaderNoteVersion {
  readonly id: string;
  readonly targetId: string;
  readonly text: string | null;
  readonly updatedAt: string;
}
export interface ReaderNotebook {
  readonly kind: "agentic-reader-notebook";
  readonly version: 2 | 3;
  readonly review?: ReviewRecords;
  readonly epoch: string;
  readonly state: ReaderState;
  readonly noteVersions: readonly ReaderNoteVersion[];
  readonly originals: readonly string[];
  readonly reviewImports?: readonly string[];
}
export interface ReaderDelta {
  readonly epoch: string;
  readonly id: string;
  readonly change: ReaderChange | ReviewChange;
  /** The versions this edit actually observed; unseen competing edits remain. */
  readonly baseNoteIds?: readonly string[];
}
function projectedNotes(versions: readonly ReaderNoteVersion[], order: readonly ReaderNote[]): ReaderNote[] {
  const chosen = new Map<string, ReaderNoteVersion>();
  for (const version of versions) chosen.set(version.targetId, version);
  const ids = [...new Set([...order.map(note => note.targetId), ...chosen.keys()])];
  return ids.flatMap(targetId => {
    const version = chosen.get(targetId);
    return version && version.text !== null ? [{ targetId, text: version.text, updatedAt: version.updatedAt }] : [];
  });
}
export function readerNotebookFromState(source: ReaderState, context: ReaderContext, originals: readonly string[] = []): ReaderNotebook {
  const state = stateOf(source, contextOf(context));
  return { kind: "agentic-reader-notebook", version: 3, review: emptyReviewRecords(), epoch: "initial", state, noteVersions: state.notes.map(note => ({ id: "legacy:" + exactJson([note.targetId, note.text, note.updatedAt]), ...note })), originals: [...originals] };
}
export function emptyReaderNotebook(context: ReaderContext): ReaderNotebook { return readerNotebookFromState(emptyReaderState(context), context); }
export function validateReaderNotebook(source: unknown, context: ReaderContext): ReaderNotebook {
  const scope = contextOf(context);
  const item = record(source, "Reader notebook", ["kind", "version", "epoch", "state", "noteVersions", "originals"], ["review", "reviewImports"]);
  if (item.kind !== "agentic-reader-notebook" || (item.version !== 2 && item.version !== 3)) invalid("Notebook exports must use the supported notebook kind and version 2 or 3.");
  if (item.version === 3 && item.review === undefined) invalid("Notebook version 3 needs review records.");
  const state = stateOf(item.state, scope), epoch = string(item.epoch, "Notebook epoch", true);
  const noteVersions = array(item.noteVersions, "Note versions").map(value => {
    const version = record(value, "Note version", ["id", "targetId", "text", "updatedAt"]);
    const targetId = string(version.targetId, "Version targetId"); reference(targetId, scope.targetIds, "Version targetId");
    return { id: string(version.id, "Version ID", true), targetId, text: version.text === null ? null : string(version.text, "Version text", true), updatedAt: timestamp(version.updatedAt, "Version updatedAt") };
  });
  if (new Set(noteVersions.map(version => version.id)).size !== noteVersions.length) invalid("Note version IDs must be unique.");
  const projected = projectedNotes(noteVersions, state.notes);
  if (exactJson(projected) !== exactJson(state.notes)) invalid("Notebook notes must match their retained versions.");
  const originals = array(item.originals, "Original saved data").map(value => string(value, "Original saved data"));
  return { kind: "agentic-reader-notebook", version: 3, epoch, state, noteVersions, originals, reviewImports: item.reviewImports === undefined ? [] : array(item.reviewImports, "Imported review identities").map(value => string(value, "Imported review identity")), review: item.review === undefined ? emptyReviewRecords() : validateReview(item.review) };
}
/** Version 1 exports are accepted and kept verbatim for recovery during migration. */
export function decodeReaderNotebook(raw: string, context: ReaderContext): ReaderNotebook {
  let value: unknown;
  try { value = JSON.parse(raw); } catch { invalid("Reader data is not valid JSON."); }
  if (typeof value === "object" && value !== null && Object.prototype.hasOwnProperty.call(value, "owner")) {
    const envelope = record(value, "Notebook recovery envelope", ["version", "owner", "value"]);
    const owner = record(envelope.owner, "Notebook owner", ["kind", "reportId", "revision"]);
    if (envelope.version !== 1 || owner.kind !== "notebook" || owner.reportId !== context.reportId || owner.revision !== context.revision) invalid("The recovered record belongs to a different record type, report or revision.");
    const notebook = validateReaderNotebook(envelope.value, context);
    return { ...notebook, originals: [...new Set([...notebook.originals, raw])] };
  }
  if (typeof value === "object" && value !== null && (value as { version?: unknown }).version === 1) return readerNotebookFromState(decodeReaderState(raw, context), context, [raw]);
  const notebook = validateReaderNotebook(value, context);
  return (value as {version?:number})?.version === 2 ? { ...notebook, originals: [...new Set([...notebook.originals, raw])] } : notebook;
}
export function encodeReaderNotebook(notebook: ReaderNotebook, context: ReaderContext): string { return exactJson(validateReaderNotebook(notebook, context)); }
export function noteVersionIds(notebook: ReaderNotebook, targetId: string): string[] { return notebook.noteVersions.filter(version => version.targetId === targetId).map(version => version.id); }
export function applyReaderDelta(source: ReaderNotebook, delta: ReaderDelta, context: ReaderContext, recordActivity = true): ReaderNotebook {
  const notebook = validateReaderNotebook(source, context);
  if (delta.epoch !== notebook.epoch) invalid("This notebook was replaced in another open copy. Export your session records before continuing.");
  string(delta.id, "Edit ID", true);
  if (delta.change.type === "annotation" || delta.change.type === "review-bookmark") return { ...notebook, review: applyReview(notebook.review || emptyReviewRecords(), delta.change) };
  if (delta.change.type !== "note") return { ...notebook, state: updateReaderState(notebook.state, delta.change, context) };
  const base = new Set(uniqueIds(delta.baseNoteIds || [], "Observed note versions"));
  const change = delta.change;
  const changed = updateReaderState(recordActivity ? notebook.state : { ...notebook.state, activity: [], droppedActivityCount: 0, nextSequence: 1 }, change, context);
  const state = recordActivity ? changed : { ...notebook.state, notes: changed.notes };
  const version: ReaderNoteVersion = { id: delta.id, targetId: change.targetId, text: change.text === "" ? null : change.text, updatedAt: change.at };
  const prior = notebook.noteVersions.find(candidate => candidate.id === version.id);
  if (prior) {
    if (exactJson(prior) !== exactJson(version)) invalid("An edit identifier conflicts with another note version.");
    return notebook;
  }
  const noteVersions = [...notebook.noteVersions.filter(candidate => candidate.targetId !== change.targetId || !base.has(candidate.id)), version];
  return { ...notebook, state: { ...state, notes: projectedNotes(noteVersions, state.notes) }, noteVersions };
}

/** Merge portable reader contributions without selecting a winner among competing edits. */
export function mergeReaderNotebooks(left: ReaderNotebook, right: ReaderNotebook, context: ReaderContext): ReaderNotebook {
  const a=validateReaderNotebook(left,context),b=validateReaderNotebook(right,context);
  if(a.epoch!==b.epoch)throw new Error('The review copy and browser notebook have different replacement epochs. Export both before replacing either.');
  const notes=new Map(a.noteVersions.map(version=>[version.id,version]));
  for(const version of b.noteVersions){const old=notes.get(version.id);if(old&&exactJson(old)!==exactJson(version))throw new Error('A note version conflicts with the imported copy.');notes.set(version.id,version);}
  const annotations=new Map((a.review?.versions||[]).map(version=>[version.id,version]));
  for(const version of b.review?.versions||[]){const old=annotations.get(version.id);if(old&&exactJson(old)!==exactJson(version))throw new Error('An annotation version conflicts with the imported copy.');annotations.set(version.id,version);}
  const bookmarks=new Map([...(a.review?.bookmarks||[]),...(b.review?.bookmarks||[])].map(anchor=>[exactJson(anchor),anchor]));
  const noteVersions=[...notes.values()];
  return validateReaderNotebook({...a,reviewImports:[...new Set([...(a.reviewImports||[]),...(b.reviewImports||[])])],noteVersions,state:{...a.state,notes:projectedNotes(noteVersions,[...a.state.notes,...b.state.notes]),bookmarks:[...new Set([...a.state.bookmarks,...b.state.bookmarks])]},review:{versions:[...annotations.values()],bookmarks:[...bookmarks.values()]},originals:[...new Set([...a.originals,...b.originals])]},context);
}
/** Explicit imports can retain feedback from an older revision as unresolved context. */
export function importReaderReview(raw: string, context: ReaderContext): ReaderNotebook {
  try { return decodeReaderNotebook(raw,context); } catch (originalError) {
    let payload: Record<string,unknown>;try{payload=JSON.parse(raw);}catch{throw originalError;}
    // Revision migration must not unwrap a foreign or malformed storage envelope.
    // Its owner is evidence, not metadata that can be discarded on a failed decode.
    let wrapped: unknown = payload;
    if (payload && typeof payload === 'object' && Object.prototype.hasOwnProperty.call(payload, 'owner')) {
      const envelope = record(payload, 'Notebook recovery envelope', ['version', 'owner', 'value']);
      const owner = record(envelope.owner, 'Notebook owner', ['kind', 'reportId', 'revision']);
      const value = envelope.value as { state?: ReaderState } | null;
      if (envelope.version !== 1 || owner.kind !== 'notebook' || owner.reportId !== context.reportId || !value?.state || owner.reportId !== value.state.reportId || owner.revision !== value.state.revision) throw originalError;
      wrapped = envelope.value;
    }
    if(!wrapped||typeof wrapped!=='object')throw originalError;
    const candidate=wrapped as Record<string,unknown>,state=(candidate.kind==='agentic-reader-notebook'?candidate.state:candidate) as ReaderState;
    if(!state||state.reportId!==context.reportId||!Array.isArray(state.notes)||!Array.isArray(state.bookmarks)||!Array.isArray(state.activity))throw originalError;
    const targets=[...(Array.isArray(candidate.noteVersions)?candidate.noteVersions.map(version=>version.targetId):[]),...state.notes.map(note=>note.targetId),...state.bookmarks,...state.activity.flatMap(action=>action.targetId?[action.targetId]:[])];
    const ownContext:ReaderContext={reportId:state.reportId,revision:state.revision,targetIds:[...new Set(targets)],viewIds:[...new Set([...(state.viewId?[state.viewId]:[]),...state.activity.flatMap(action=>action.viewId?[action.viewId]:[])])],journeyIds:state.journeyId?[state.journeyId]:[],activityLimit:context.activityLimit};
    const previous=decodeReaderNotebook(exactJson(wrapped),ownContext),fresh=emptyReaderNotebook(context);
    const anchor=(id:string)=>({kind:'section' as const,target:{reportId:previous.state.reportId,revision:previous.state.revision,id,label:id,path:[],fingerprint:'unavailable',excerpt:'This earlier notebook did not include the original target text.'}});
    return {...fresh,originals:[...previous.originals,raw],review:{versions:[...(previous.review?.versions||[]),...previous.noteVersions.map(version=>({id:'import:'+version.id,annotationId:'legacy:'+version.targetId,anchor:anchor(version.targetId),text:version.text,at:version.updatedAt,draft:false}))],bookmarks:[...(previous.review?.bookmarks||[]),...previous.state.bookmarks.map(anchor)]}};
  }
}
