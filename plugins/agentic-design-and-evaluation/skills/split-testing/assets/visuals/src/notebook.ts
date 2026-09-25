import { exactJson } from './exact-json';
import type { SearchEntry } from './report-search';
import { anchorLabel, anchorContext, anchorEvidence } from './review-presentation';
import { createNotebookView, NotebookView } from './notebook-view';
import { readerDate } from './review-presentation';
import { selectedFigureItems } from './item-selection';
import { NotificationMessage } from './notifications';
import { fingerprint } from './identity';
import { createTargetRegistry, readableReviewText, TargetRegistry } from './review-targets';
import { attachContextReview, ContextReviewController } from './context-review';
import { ReviewChange, emptyReviewRecords } from './review-state';
import { annotatedReport, reviewHandoff, retainReportRecipe, readReviewSeed } from './review-export';
import { downloadBlob } from './figure-export';
import { escapeText as e } from "./core";
import {
  DEFAULT_READER_ACTIVITY_LIMIT, ReaderContext, ReaderState, ReaderChange, ReaderNotebook, ReaderDelta,
  emptyReaderNotebook, decodeReaderNotebook, mergeReaderNotebooks, importReaderReview, encodeReaderNotebook, validateReaderNotebook, applyReaderDelta, noteVersionIds,
} from "./reader-state";
import { createOwnedStore, OwnedStore, OwnedStoreResult } from "./reader-storage";

export interface ResearchNotebookInput { id: string; scopeId: string; revision: string; storageKey?: string; activityLimit?: number }
export interface ReaderPlace { viewId: string | null; mode: "single" | "all"; journeyId: string | null }
export interface NotebookHooks {
  notify?(message:NotificationMessage):void;
  reveal(target: HTMLElement): void;
  navigate(scope: HTMLElement, place: ReaderPlace): void;
  restored?(scope: HTMLElement, place: ReaderPlace): void;
  now?: () => string;
  controls?(element: HTMLElement): HTMLElement | null;
}
export interface NotebookController {
  searchEntries(scope: HTMLElement): SearchEntry[];
  whenReady(): Promise<void>;
  hasReview(figure: HTMLElement): boolean;
  reviewSelection(figure: HTMLElement, action: 'note' | 'bookmark', trigger: HTMLElement): void;
  click(target: Element): boolean;
  change(target: Element): boolean;
  input(target: Element): boolean;
  restore(scope: HTMLElement): ReaderPlace | null;
  recordPlace(scope: HTMLElement, place: ReaderPlace): void;
  recordInspection(target: HTMLElement): void;
  /** Wait for already requested persistence/transfers; attachment itself remains synchronous. */
  whenIdle(): Promise<void>;
  cleanup(): void;
}

function identifier(value: string): string {
  if (typeof value !== "string" || !/^[A-Za-z][A-Za-z0-9_.:-]*$/.test(value)) throw new TypeError("A notebook ID must begin with a letter and use letters, numbers, underscores, periods, colons or hyphens.");
  return value;
}

/** A native optional panel; live controls are created only by the local controller. */
export function researchNotebook(input: ResearchNotebookInput): string {
  identifier(input.id); identifier(input.scopeId);
  if (typeof input.revision !== "string" || input.revision.length === 0) throw new TypeError("Supply a nonempty notebook revision.");
  if (input.storageKey !== undefined && (typeof input.storageKey !== "string" || input.storageKey.length === 0)) throw new TypeError("Supply a nonempty notebook storage key or omit it.");
  if (input.activityLimit !== undefined && (!Number.isSafeInteger(input.activityLimit) || input.activityLimit < 0)) throw new TypeError("Notebook activityLimit must be a nonnegative safe integer.");
  return '<details class="av-notebook" id="' + e(input.id) + '" data-av-notebook data-av-notebook-scope="' + e(input.scopeId) + '" data-av-notebook-revision="' + e(input.revision) + '"' + (input.storageKey === undefined ? "" : ' data-av-notebook-storage-key="' + e(input.storageKey) + '"') + (input.activityLimit === undefined ? "" : ' data-av-notebook-limit="' + input.activityLimit + '"') + '><summary>Your notebook</summary><div class="av-notebook-popover"><p class="av-notebook-status" data-av-notebook-status role="status" aria-live="polite">Enable JavaScript to use notes and bookmarks.</p><div class="av-notebook-panel" data-av-notebook-panel hidden></div></div></details>';
}

interface Draft { text: string; at: string; id: string; baseNoteIds: string[] }
interface Memory { epochKnown: boolean; state: ReaderState; notebook: ReaderNotebook; drafts: Map<string, Draft>; lockedRaw: string | null; lockMessage: string; persistence: string; readBlocked: boolean; work: Promise<void>; stopped: boolean }
const retained = new WeakMap<HTMLElement, Map<string, Memory>>();
interface Target { element: HTMLElement; label: string }
interface Route { label: string; steps: string[] }
interface Panel {
  view: NotebookView;
  recordsKey?: string;
  activityKey?: string;
  count: HTMLElement;
  inclusions: HTMLElement;
  activityLimit: number;
  element: HTMLElement;
  content: HTMLElement;
  status: HTMLElement;
  selected: string;
  target: HTMLSelectElement;
  note: HTMLTextAreaElement;
  bookmark: HTMLInputElement;
  notes: HTMLElement;
  bookmarks: HTMLElement;
  activity: HTMLElement;
  historyStatus: HTMLElement;
  resume: HTMLButtonElement;
  recover: HTMLAnchorElement;
  download: HTMLAnchorElement;
  conflicts: HTMLElement;
  confirmation: HTMLElement;
  confirmationText: HTMLElement;
  importConfirm: HTMLButtonElement;
  importCancel: HTMLButtonElement;
  resetConfirm: HTMLButtonElement;
  resetCancel: HTMLButtonElement;
}
type Pending = { kind: "reading" } | { kind: "reset" } | { kind: "import"; state: ReaderNotebook; name: string } | null;
interface Session extends Memory {
  scope: HTMLElement;
  registry: TargetRegistry;
  reviewUI?: ContextReviewController;
  seed?: ReaderNotebook;
  seedKey?: string;
  seedInvalid?: boolean;
  context: ReaderContext;
  signature: string;
  key: string | null;
  store: OwnedStore<ReaderNotebook> | null;
  writes: NotebookWrite[];
  loading: boolean;
  saving: boolean;
  changed: boolean;
  exportJob: Promise<void> | null;
  importJob?: Promise<void>;
  exportBusy?: boolean;
  initialFocus: Element | null;
  targets: Map<string, Target>;
  views: Map<string, Target>;
  routes: Map<string, Route>;
  panels: Panel[];
  notice: string;
  pending: Pending;
  token: number;
}

const documentSessions = new WeakMap<Document, Map<HTMLElement, Session>>();

type NotebookWrite = { delta: ReaderDelta; epochUnobserved?: boolean } | { replacement: ReaderNotebook; expected: ReaderNotebook };
let editSequence = 0;
const writerId = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
function editId(): string { return writerId + "-" + (++editSequence); }

/** Event handlers are called by the owning enhancement root; no global listeners are added. */
export function attachNotebooks(root: HTMLElement, hooks: NotebookHooks): NotebookController {
  const document = root.ownerDocument;
  const peers = documentSessions.get(document) || new Map<HTMLElement, Session>(); documentSessions.set(document, peers);
  try { retainReportRecipe(document); } catch { /* Explicit export reports an invalid recipe without disabling notes. */ }
  const now = hooks.now || (() => new Date().toISOString());
  const undo: (() => void)[] = [];
  const sessions = new Map<HTMLElement, Session>();
  const initialReads: Promise<void>[] = [];
  const panels = new Map<HTMLElement, { panel: Panel; session: Session }>();
  const owners = new WeakMap<HTMLElement, Session>();
  let cleaned = false;
  const all = <T extends Element = HTMLElement>(selector: string): T[] => [...(root.matches(selector) ? [root as unknown as T] : []), ...Array.from(root.querySelectorAll<T>(selector))];
  function children(element: HTMLElement): void {
    const original = Array.from(element.childNodes);
    undo.push(() => { element.textContent = ""; for (const node of original) element.appendChild(node); });
  }
  function attribute(element: Element, name: string): void {
    const original = element.getAttribute(name);
    undo.push(() => original === null ? element.removeAttribute(name) : element.setAttribute(name, original));
  }
  function append<K extends keyof HTMLElementTagNameMap>(parent: HTMLElement, tag: K, className = "", text?: string): HTMLElementTagNameMap[K] {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    parent.appendChild(element); return element;
  }
  function button(parent: HTMLElement, action: string, text: string): HTMLButtonElement {
    const element = append(parent, "button", "av-button av-button-quiet", text);
    element.setAttribute("type", "button"); element.setAttribute("data-av-notebook-action", action); return element;
  }
  function link(parent: HTMLElement, action: string, text: string): HTMLAnchorElement {
    const element = append(parent, "a", "av-button av-button-quiet", text);
    element.setAttribute("href", "#"); element.setAttribute("data-av-notebook-action", action); return element;
  }
  function labelOf(element: HTMLElement): string {
    const labelledBy = (element.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean).map(id => document.getElementById(id)?.textContent || "").filter(Boolean).join(" ");
    const own = (heading: HTMLElement): boolean => !heading.closest("[data-av-notebook]") && heading.closest(".av-card,[data-av-panel],.av-surface,.av-workspace") === element;
    const heading = Array.from(element.querySelectorAll<HTMLElement>("h1,h2,h3,h4,h5,h6")).find(own) || Array.from(element.querySelectorAll<HTMLElement>("summary")).find(own);
    return element.getAttribute("aria-label") || labelledBy || heading?.textContent?.trim() || element.id;
  }
  function distinctLabels(targets: Map<string, Target>, scope: HTMLElement): void {
    const visible = (text: string) => text.replace(/[ \t\n\r\f]+/g, " ").trim();
    const collisions = () => {
      const groups = new Map<string, [string, Target][]>();
      for (const pair of targets) { const name = visible(pair[1].label); const group = groups.get(name) || []; group.push(pair); groups.set(name, group); }
      return [...groups.values()].filter(group => group.length > 1).flat();
    };
    for (const [, target] of collisions()) {
      const context = target.element.parentElement?.closest<HTMLElement>("[data-av-panel],.av-card");
      if (context && scope.contains(context) && visible(labelOf(context)) !== visible(target.label)) target.label += " — " + labelOf(context);
    }
    // Recheck the complete set: authored text can itself match a qualified label.
    for (let repeated = collisions(); repeated.length; repeated = collisions()) {
      for (const [id, target] of repeated) target.label += " [" + exactJson(id) + "]";
    }
  }
  function prepare(element: HTMLElement): { content: HTMLElement; status: HTMLElement } {
    attribute(element, "open"); attribute(element, "data-av-notebook-error");
    let content = element.querySelector<HTMLElement>("[data-av-notebook-panel]");
    if (!content) { content = append(element, "div", "av-notebook-panel"); content.setAttribute("data-av-notebook-panel", ""); undo.push(() => content!.remove()); }
    let status = element.querySelector<HTMLElement>("[data-av-notebook-status]");
    if (!status) { status = append(element, "p", "av-notebook-status"); status.setAttribute("data-av-notebook-status", ""); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); undo.push(() => status!.remove()); }
    children(content); children(status); attribute(content, "hidden");
    content.textContent = ""; content.hidden = true;
    return { content, status };
  }
  function fail(element: HTMLElement, content: HTMLElement, status: HTMLElement, message: string): void {
    content.hidden = true; status.textContent = message; element.setAttribute("data-av-notebook-error", ""); element.setAttribute("open", "");
  }
  function contextual(state: ReaderState, session: Pick<Session, "routes">): ReaderState {
    if (state.journeyId !== null && (state.viewId === null || !session.routes.get(state.journeyId)?.steps.includes(state.viewId))) throw new Error("The saved reading route does not include its saved view. The original notebook is protected for recovery.");
    return state;
  }
  function invalidateExports(session: Session): void {
    for (const panel of session.panels) { panel.download.hidden = true; panel.download.setAttribute("href", "#"); panel.download.removeAttribute("download"); }
  }
  function assign(session: Session, notebook: ReaderNotebook): void {
    contextual(notebook.state, session); session.notebook = notebook; session.state = notebook.state; invalidateExports(session);
  }
  function snapshot(session: Session): ReaderNotebook {
    let notebook = session.notebook;
    for (const [targetId, draft] of session.drafts) notebook = applyReaderDelta(notebook, { epoch: notebook.epoch, id: draft.id, baseNoteIds: draft.baseNoteIds, change: { type: "note", targetId, text: draft.text, at: draft.at } }, session.context, false);
    // Draft export preserves text/versions without inventing save/history actions.
    return { ...notebook, state: { ...session.state, notes: notebook.state.notes } };
  }
  function storageMessage(session: Session): string {
    return session.lockedRaw !== null ? session.lockMessage + " The original saved data stays protected and can be downloaded." : session.persistence;
  }
  function writeTo(notebook: ReaderNotebook, write: NotebookWrite, context: ReaderContext): ReaderNotebook {
    if ("delta" in write) return applyReaderDelta(notebook, write.delta, context);
    if (encodeReaderNotebook(notebook, context) !== encodeReaderNotebook(write.expected, context)) throw new Error("Saved records changed before replacement.");
    return write.replacement;
  }
  function blocked(session: Session, result: OwnedStoreResult<ReaderNotebook>): void {
    session.stopped = true; session.readBlocked = true;
    if (result.status === "blocked" || result.status === "unavailable") {
      if (result.raw !== undefined) { session.lockedRaw = result.raw; session.lockMessage = result.message; }
      session.persistence = result.message;
    }
    session.writes = [];
  }
  function includeSeed(session: Session, current: ReaderNotebook | null): ReaderNotebook {
    const notebook=current || (session.seed ? {...emptyReaderNotebook(session.context),epoch:session.seed.epoch} : emptyReaderNotebook(session.context));
    if(!session.seed||!session.seedKey||notebook.reviewImports?.includes(session.seedKey))return notebook;
    const combined=mergeReaderNotebooks(notebook,session.seed,session.context);
    return {...combined,reviewImports:[...(combined.reviewImports||[]),session.seedKey]};
  }
  async function refreshForExport(session: Session, requireCurrent = true): Promise<void> {
    await settled(session);
    if(!session.store||session.stopped)return;
    const latest=await session.store.read();
    if(latest.status==='ready'&&!session.loading&&!session.saving&&!session.writes.length){
      let current:ReaderNotebook;
      try{current=includeSeed(session,latest.value===null?null:validateReaderNotebook(latest.value,session.context));}
      catch(error){if(requireCurrent)throw error;session.notebook={...session.notebook,originals:[...new Set([...session.notebook.originals,exactJson(latest.value)])]};return;}
      if(current.epoch===session.notebook.epoch)assign(session,current);
      else if(!requireCurrent)session.notebook={...session.notebook,originals:[...new Set([...session.notebook.originals,encodeReaderNotebook(current,session.context)])]};
      else throw new Error('Another copy replaced this notebook. Export the current notebook data for recovery before preparing a reviewed report.');
    }else if(latest.status==='blocked'||latest.status==='unavailable')blocked(session,latest);
  }
  function persist(session: Session): void {
    if (session.loading || session.saving || session.stopped || !session.store || !session.writes.length) return;
    session.saving = true; session.persistence = "Saving your notebook… Keep this report open until saving finishes.";
    session.work = (async () => {
      while (session.writes.length && !session.stopped) {
        const batch = session.writes.slice();
        const result = await session.store!.update(current => {
          let notebook = includeSeed(session, current === null ? null : validateReaderNotebook(current, session.context));
          contextual(notebook.state, session);
          for (const write of batch) notebook = writeTo(notebook, write, session.context);
          return notebook;
        });
        if (result.status !== "saved" || result.value === null) { blocked(session, result); break; }
        session.writes.splice(0, batch.length);
        try {
          let notebook = validateReaderNotebook(result.value, session.context);
          for (const write of session.writes) notebook = writeTo(notebook, write, session.context);
          assign(session, notebook);
          session.persistence = "Saved in this browser. Other open copies are combined when saving.";
        } catch {
          blocked(session, { status: "blocked", raw: encodeReaderNotebook(result.value, session.context), message: "Another open copy changed the records before your replacement. Your current session and the saved copy remain separately recoverable." });
        }
        render(session);
      }
    })().catch(() => blocked(session, { status: "unavailable", message: "Browser saving failed. Your records stay in this open report; export a copy to keep them." })).finally(() => {
      session.saving = false; if (cleaned) session.store?.close(); render(session);
    });
  }
  async function settled(session: Session): Promise<void> {
    do { await session.work; } while (session.loading || session.saving);
  }
  function apply(session: Session, change: ReaderChange | ReviewChange, notice = "", bases?: string[]): boolean {
    try {
      const delta: ReaderDelta = { epoch: session.notebook.epoch, id: editId(), change, ...(change.type === "note" ? { baseNoteIds: bases || session.drafts.get(change.targetId)?.baseNoteIds || noteVersionIds(session.notebook, change.targetId).slice(-1) } : {}) };
      const deltas=[delta];
      const anchor=change.type==='review-bookmark'?change.anchor:change.type==='annotation'&&!change.version.draft?change.version.anchor:null;
      if(anchor){
        const action=change.type==='review-bookmark'?(change.enabled?'bookmark-added':'bookmark-removed'):change.type==='annotation'&&change.version.text===null?'note-removed':'note-saved';
        deltas.push({epoch:session.notebook.epoch,id:editId(),change:{type:'activity',action,at:change.type==='annotation'?change.version.at:now(),...(session.targets.has(anchor.target.id)?{targetId:anchor.target.id}:{})}});
      }
      // Validate the complete in-session change before queueing it. Persistence
      // merges both deltas inside the same owned transaction.
      let next=session.notebook;for(const item of deltas)next=applyReaderDelta(next,item,session.context);
      assign(session,next);
      session.changed = true; session.notice = notice;
      if (session.store && !session.stopped) { session.writes.push(...deltas.map(delta=>({ delta, epochUnobserved: !session.epochKnown }))); persist(session); }
      render(session); return true;
    } catch (error) { session.notice = error instanceof Error ? error.message : "This notebook change could not be saved."; render(session); return false; }
  }
  function replace(session: Session, source: ReaderNotebook, notice: string): void {
    const expected = session.notebook, replacement = { ...source, epoch: editId(), reviewImports: [...new Set([...(source.reviewImports||[]),...(session.notebook.reviewImports||[]),...(session.seedKey?[session.seedKey]:[])])] };
    assign(session, replacement); session.epochKnown = true; session.drafts.clear(); session.changed = true; session.notice = notice;
    if (session.store && !session.stopped) { session.writes.push({ replacement, expected }); persist(session); }
  }
  async function initialize(session: Session, cached?: Memory): Promise<void> {
    if (!session.store) return;
    if (cached) { await cached.work; session.stopped ||= cached.stopped; session.readBlocked ||= cached.readBlocked; }
    const result = await session.store.read();
    const value = result.value;
    if (value !== undefined && value !== null) {
      try {
        let notebook = validateReaderNotebook(value, session.context); contextual(notebook.state, session);
        notebook = includeSeed(session, notebook);
        if (!cached?.stopped) {
          const writes: NotebookWrite[] = [];
          for (const pending of session.writes) {
            // Pre-hydration actions have not observed a stored epoch. Their note
            // bases stay empty, preserving unseen saved notes as conflicts.
            const write: NotebookWrite = "delta" in pending && pending.epochUnobserved ? { delta: { ...pending.delta, epoch: notebook.epoch } } : pending;
            notebook = writeTo(notebook, write, session.context); writes.push(write);
          }
          session.writes = writes; assign(session, notebook);
        }
      } catch {
        blocked(session, { status: "blocked", raw: exactJson(value), message: "The saved notebook is incompatible with this report. Its original data remains protected." });
      }
    }
    if (result.status === "ready" || result.status === "saved") session.epochKnown = true;
    if (result.status === "blocked" || result.status === "unavailable") blocked(session, result);
    else if (!session.stopped && (result.status === "ready" || result.status === "saved")) session.persistence = result.source === "legacy" ? "Earlier notebook loaded. Saving migrates it while retaining the original localStorage bytes." : result.source === "database" ? "Your saved notebook is ready." : "No notebook has been saved in this browser yet.";
    let explicit = false;
    try {
      const hash = session.scope.ownerDocument.defaultView?.location.hash || "";
      const target = hash.startsWith("#") ? document.getElementById(decodeURIComponent(hash.slice(1))) : null;
      explicit = target !== null && session.scope.contains(target);
    } catch { /* A malformed fragment does not cancel another report's saved place. */ }
    const focusMoved = document.activeElement !== session.initialFocus && session.scope.contains(document.activeElement);
    if (!cleaned && !session.changed && !explicit && !focusMoved && !session.stopped) { const saved = place(session); if (saved) (hooks.restored || hooks.navigate)(session.scope, saved); }
  }
  function place(session: Session): ReaderPlace | null {
    return session.state.viewId === null ? null : { viewId: session.state.viewId, mode: session.state.mode, journeyId: session.state.journeyId };
  }
  function capture(panel: Panel, session: Session): void {
    const previous = session.drafts.get(panel.selected)?.text ?? session.state.notes.find(note => note.targetId === panel.selected)?.text ?? "";
    if (panel.note.value === previous) return;
    invalidateExports(session);
    const saved = session.state.notes.find(note => note.targetId === panel.selected)?.text ?? "";
    if (panel.note.value === saved) session.drafts.delete(panel.selected);
    else session.drafts.set(panel.selected, { text: panel.note.value, at: now(), id: editId(), baseNoteIds: session.drafts.get(panel.selected)?.baseNoteIds || noteVersionIds(session.notebook, panel.selected).slice(-1) });
  }
  function actionItem(parent: HTMLElement, action: string, text: string, targetId: string): HTMLButtonElement {
    const control = button(parent, action, text); control.setAttribute("data-av-notebook-target-id", targetId); return control;
  }
  function activityLabel(entry: ReaderState["activity"][number], session: Session): string {
    const target = entry.targetId === undefined ? "" : session.targets.get(entry.targetId)?.label || entry.targetId;
    const view = entry.viewId === undefined ? "" : session.views.get(entry.viewId)?.label || entry.viewId;
    const labels: Record<string, string> = { "open-view": "Opened", "bookmark-added": "Bookmarked", "bookmark-removed": "Removed bookmark from", "note-saved": "Saved a note on", "note-removed": "Removed a note from", inspect: "Opened for inspection", "return-to": "Returned to" };
    return (Object.prototype.hasOwnProperty.call(labels, entry.action) ? labels[entry.action] : entry.action) + (view || target ? " “" + (view || target) + "”" : "");
  }
  function importedSummary(value: ReaderNotebook): string {
    const versions = value.review?.versions || [];
    const annotations = new Set(versions.filter(version => version.text !== null && !version.draft).map(version => version.annotationId)).size;
    const drafts = new Set(versions.filter(version => version.text !== null && version.draft).map(version => version.annotationId)).size;
    const bookmarks = value.state.bookmarks.length + (value.review?.bookmarks.length || 0);
    const older = value.state.notes.length;
    return `${annotations} ${annotations === 1 ? 'annotation' : 'annotations'}, ${drafts} ${drafts === 1 ? 'draft' : 'drafts'}, ${bookmarks} ${bookmarks === 1 ? 'bookmark' : 'bookmarks'}${older ? ` and ${older} earlier ${older === 1 ? 'note' : 'notes'}` : ''}`;
  }
  function render(session: Session): void {
    if (cleaned) return;
    for (const panel of session.panels) {
      panel.status.textContent = [session.notice, storageMessage(session)].filter(Boolean).join(" ");
      panel.target.value = panel.selected;
      const count=new Set((session.notebook.review?.versions||[]).filter(v=>v.text!==null).map(v=>v.annotationId)).size+session.state.notes.length+session.state.bookmarks.length+(session.notebook.review?.bookmarks.length||0);
      panel.count.textContent=String(count);panel.count.hidden=!count;
      for(const control of Array.from(panel.content.querySelectorAll<HTMLButtonElement>('[data-av-notebook-action="export"],[data-av-notebook-action="export-report"],[data-av-notebook-action="export-handoff"],[data-av-notebook-action="copy-handoff"]'))){control.disabled=!!session.exportBusy;control.setAttribute('aria-busy',String(!!session.exportBusy));}
      const text = session.drafts.get(panel.selected)?.text ?? session.state.notes.find(note => note.targetId === panel.selected)?.text ?? "";
      if (panel.note.value !== text) panel.note.value = text;
      panel.bookmark.checked = session.state.bookmarks.includes(panel.selected);
      const recordsKey=exactJson([session.state.notes,session.state.bookmarks,session.notebook.noteVersions]);
      const recordsChanged=panel.recordsKey!==recordsKey;panel.recordsKey=recordsKey;
      if(recordsChanged){
      for(const child of Array.from(panel.notes.children))if(!child.hasAttribute('data-av-review-entry'))child.remove();
      for (const note of session.state.notes) {
        const item = append(panel.notes, "li", "av-review-card");item.setAttribute('data-av-legacy-note',note.targetId);item.setAttribute('data-av-notebook-target-id',note.targetId);item.setAttribute('data-av-entry-state','attention');
        append(item,'h4','',session.targets.get(note.targetId)!.label);
        append(item,'p','av-review-meta','Earlier note · verify attachment');
        append(item, "pre", "av-notebook-note", note.text);
        const actions=append(item,'div','av-review-card-actions');actionItem(actions, "edit-note", "Edit earlier note", note.targetId);
        append(item, "p", "av-muted", "This note identifies a report part, but has no original evidence fingerprint. Verify the content before relying on its attachment.");
      }

      panel.conflicts.textContent = "";
      const versionsByTarget = new Map<string, Array<(typeof session.notebook.noteVersions)[number]>>();
        for (const version of session.notebook.noteVersions) { const group = versionsByTarget.get(version.targetId) || []; group.push(version); versionsByTarget.set(version.targetId, group); }
        const competing = new Set([...versionsByTarget].filter(([, versions]) => versions.length > 1).map(([id]) => id));
      for (const targetId of competing) {
        const item = append(panel.conflicts, "li"); append(item, "p", "", "Competing versions of “" + session.targets.get(targetId)!.label + "”. All versions are included in exports until you choose one.");
        for (const [index, version] of versionsByTarget.get(targetId)!.entries()) {
          append(item, "p", "av-muted", "Version " + (index + 1) + " · " + version.updatedAt);
          append(item, "pre", "av-notebook-note", version.text === null ? "[Note removed in this version]" : version.text);
          const choice = actionItem(item, "resolve-note", "Keep version " + (index + 1), targetId); choice.setAttribute("data-av-notebook-version-id", version.id);
          choice.setAttribute("aria-label", "Keep version " + (index + 1) + " of the note on " + session.targets.get(targetId)!.label);
        }
      }
      panel.conflicts.hidden = !competing.size;
      const conflictsHeading = panel.conflicts.previousElementSibling as HTMLElement | null;
      if (conflictsHeading?.tagName.toLowerCase() === 'h3') conflictsHeading.hidden = !competing.size;
      }
      const legacy = panel.note.closest<HTMLElement>('.av-notebook-legacy');
      if (legacy) legacy.hidden = !session.notebook.noteVersions.length && !session.state.bookmarks.length && !session.drafts.size;
      const bookmarkTarget = panel.content.querySelector<HTMLButtonElement>('[data-av-notebook-action="bookmark-target"]');
      const selectedTarget = session.targets.get(panel.selected)?.element;
      if (bookmarkTarget && selectedTarget) {
        const kind = selectedTarget.hasAttribute('data-av-figure') ? 'figure' : 'section';
        const active = (session.notebook.review?.bookmarks || []).some(anchor => anchor.kind === kind && anchor.target.id === panel.selected && session.registry.resolve(anchor).status === 'resolved');
        bookmarkTarget.setAttribute('aria-pressed', String(active));
        bookmarkTarget.textContent = active ? 'Remove bookmark' : 'Bookmark this part';
      }

      if(recordsChanged){
      for(const child of Array.from(panel.bookmarks.children))if(!child.hasAttribute('data-av-review-bookmark'))child.remove();
      for (const targetId of session.state.bookmarks) {
        const item=append(panel.bookmarks,'li','av-review-card');item.setAttribute('data-av-legacy-bookmark',targetId);item.setAttribute('data-av-notebook-target-id',targetId);item.setAttribute('data-av-entry-state','attention');
        append(item,'h4','',session.targets.get(targetId)!.label);append(item,'p','av-review-warning','Earlier bookmark · no original evidence fingerprint. Verify this report part before relying on the attachment.');
        const actions=append(item,'div','av-review-card-actions');actionItem(actions,'open-target','Go to report part',targetId);actionItem(actions,'remove-legacy-bookmark','Remove',targetId);
      }

      }
      const activityKey=exactJson([session.state.activity,panel.activityLimit]);
      if(panel.activityKey!==activityKey){panel.activityKey=activityKey;
      panel.activity.textContent = "";
      let lastDay = '';
      for (const entry of [...session.state.activity].reverse().slice(0,panel.activityLimit)) {
        const day = new Date(entry.at).toLocaleDateString(undefined,{year:'numeric',month:'long',day:'numeric'});if(day!==lastDay){append(panel.activity,'li','av-activity-day',day);lastDay=day;}
        const item = append(panel.activity, "li");
        if (entry.viewId !== undefined) {
          const control = button(item, "open-view", activityLabel(entry, session)); control.setAttribute("data-av-notebook-view-id", entry.viewId);
        } else if (entry.targetId !== undefined) actionItem(item, "open-target", activityLabel(entry, session), entry.targetId);
        else append(item, "span", "", activityLabel(entry, session));
        const time = append(item, "time", "av-muted", readerDate(entry.at,true)); time.setAttribute("datetime", entry.at);time.title=entry.at;
      }
      if (!session.state.activity.length && session.context.activityLimit! > 0) append(panel.activity, 'li', 'av-muted', 'No recent activity.');
      }
      const more=panel.content.querySelector<HTMLElement>('[data-av-notebook-action="activity-more"]'),less=panel.content.querySelector<HTMLElement>('[data-av-notebook-action="activity-less"]');
      if(more){more.hidden=session.state.activity.length<=panel.activityLimit;more.textContent=`Show ${Math.min(20,Math.max(0,session.state.activity.length-panel.activityLimit))} more…`;}
      if(less)less.hidden=panel.activityLimit<=20;
      const limit = session.context.activityLimit!;
      panel.historyStatus.textContent = limit === 0 ? "Activity history is off. Notes, bookmarks and your place still work." : `Recent activity keeps up to ${limit} actions.${session.state.droppedActivityCount ? ` ${session.state.droppedActivityCount} earlier actions were not kept.` : ""}`;

      const savedPlace = place(session);
      panel.resume.disabled = savedPlace === null;
      panel.resume.textContent = savedPlace ? "Resume “" + session.views.get(savedPlace.viewId!)!.label + "”" : "Resume reading";
      panel.recover.hidden = session.lockedRaw === null;
      if (session.lockedRaw === null) { panel.recover.setAttribute("href", "#"); panel.recover.removeAttribute("download"); }
      panel.confirmation.hidden = session.pending === null;
      panel.importConfirm.hidden = session.pending?.kind !== "import";
      panel.importCancel.hidden = session.pending?.kind !== "import" && session.pending?.kind !== "reading";
      panel.resetConfirm.hidden = session.pending?.kind !== "reset";
      panel.resetCancel.hidden = session.pending?.kind !== "reset";
      panel.confirmationText.textContent = session.pending?.kind === "reading" ? "Reading the file you selected…" : session.pending?.kind === "reset" ? "Start a new notebook? This removes current notes, bookmarks, drafts and your saved place, and requests replacement of your compatible saved notebook. Foreign or unreadable saved data stays protected. Export anything you want to keep first." : session.pending?.kind === "import" ? `Replace this notebook with “${session.pending.name}”? It contains ${importedSummary(session.pending.state)}. Your current notes and drafts will be replaced.${session.lockedRaw !== null ? " Earlier saved data stays protected; this imported copy will remain in the session if browser saving is blocked." : ""}` : "";
    }
    session.reviewUI?.render(session.panels.map(panel => panel.notes), session.panels.map(panel => panel.bookmarks),session.panels.map(panel=>panel.inclusions));
    for(const panel of session.panels)panel.view.refresh();
  }
  function build(element: HTMLElement, content: HTMLElement, status: HTMLElement, session: Session): Panel {
    const summary=element.querySelector<HTMLElement>('summary');
    const count=append(summary||element,'span','av-notebook-count');count.setAttribute('data-av-review-ui','');count.setAttribute('aria-label','Notes and bookmarks');count.hidden=true;undo.push(()=>count.remove());
    const view = createNotebookView(element, content), { notes: notesPage, bookmarks: bookmarksPage, activity: activityPage, share: sharePage } = view.areas;
    undo.push(() => view.cleanup());
    // Status stays reachable regardless of which collection the reader scrolls.
    const statusHome = document.createComment('av-notebook-status');status.parentNode?.insertBefore(statusHome,status);view.footer.appendChild(status);
    undo.push(()=>statusHome.parentNode?.replaceChild(status,statusHome));
    const compose = append(notesPage,'div','av-notebook-compose');
    const label = append(compose, "label", "av-notebook-field", "About");
    const target = append(label, "select"); target.setAttribute("data-av-notebook-target", "");
    for (const [id, value] of session.targets) { const option = append(target, "option", "", value.label); option.value = id; }
    const actions = append(compose, "div", "av-notebook-actions");
    button(actions, "new-annotation", "Add a note");button(actions, "bookmark-target", "Bookmark this part");
    const legacy = append(notesPage, "details", "av-notebook-legacy");
    append(legacy, "summary", "", "Earlier notes by report part");
    append(legacy, "p", "av-muted", "These earlier notes identify a report part without recording its evidence fingerprint. Use Add a note for an exact content attachment.");
    const noteLabel = append(legacy, "label", "av-notebook-field", "Your earlier note");
    const note = append(noteLabel, "textarea"); note.setAttribute("rows", "5"); note.setAttribute("data-av-notebook-note", "");
    const editing = append(legacy, "div", "av-notebook-actions"); button(editing, "save-note", "Save note"); button(editing, "remove-note", "Remove note");
    const bookmarkLabel = append(legacy, "label", "av-notebook-bookmark");
    const bookmark = append(bookmarkLabel, "input"); bookmark.setAttribute("type", "checkbox"); bookmark.setAttribute("data-av-notebook-bookmark", ""); append(bookmarkLabel, "span", "", "Bookmark this part");
    append(notesPage, "h3", "av-sr-only", "Notes"); const notes = append(notesPage, "ul", "av-notebook-list"); notes.setAttribute("data-av-notebook-notes", "");
    append(notesPage, "h3", "", "Competing note versions"); const conflicts = append(notesPage, "ul", "av-notebook-list"); conflicts.setAttribute("data-av-notebook-conflicts", "");
    append(bookmarksPage, "h3", "av-sr-only", "Bookmarks"); const bookmarks = append(bookmarksPage, "ul", "av-notebook-list"); bookmarks.setAttribute("data-av-notebook-bookmarks", "");
    const resume = button(activityPage, "resume", "Resume reading");
    const history = append(activityPage, "div", "av-notebook-history"); append(history, "h3", "", "Recent activity");
    const historyStatus = append(history, "p", "av-muted"); const activity = append(history, "ol", "av-activity-list"); activity.setAttribute("data-av-notebook-activity", "");
    notesPage.appendChild(legacy);
    const historyActions=append(history,'div','av-notebook-actions');button(historyActions,'activity-more','Show more');button(historyActions,'activity-less','Show fewer');
    const transfers = append(sharePage, "div", "av-notebook-transfer");
    const annotated=append(transfers,'section','av-transfer-card');append(annotated,'h3','','Annotated report');append(annotated,'p','','A standalone interactive report with the original evidence and the feedback selected below.');button(annotated,'export-report','Download annotated report');
    const handoff=append(transfers,'section','av-transfer-card');append(handoff,'h3','','Review handoff');append(handoff,'p','','Readable Markdown for a person or agent: your feedback, exact evidence, source references, unresolved attachments and competing versions.');button(handoff,'export-handoff','Download review handoff');button(handoff,'copy-handoff','Copy review handoff');
    const selection=append(transfers,'details','av-share-selection');append(selection,'summary','','Choose what to share');append(selection,'p','av-muted','Includes all notes, drafts and bookmarks by default. Exclusions affect these two review formats only, not your notebook backup.');const inclusions=append(selection,'div','av-review-inclusions');
    const backup=append(transfers,'section','av-transfer-card');append(backup,'h3','','Notebook backup');append(backup,'p','','All reader records, including drafts, activity, competing versions and retained originals. Restore this JSON to continue reviewing.');button(backup,'export','Prepare notebook export');const download=link(backup,'download','Download notebook copy');download.hidden=true;const recover=link(backup,'recover','Download original saved data');
    const importLabel = append(backup, "label", "av-notebook-field", "Restore an exported notebook");
    const file = append(importLabel, "input"); file.setAttribute("type", "file"); file.setAttribute("accept", ".json,application/json"); file.setAttribute("data-av-notebook-import", "");
    button(backup, "start-reset", "Start a new notebook");
    const confirmation = append(view.footer, "div", "av-notebook-confirmation"); confirmation.setAttribute("data-av-notebook-confirmation", "");
    const confirmationText = append(confirmation, "p");
    const importConfirm = button(confirmation, "confirm-import", "Replace notebook"), importCancel = button(confirmation, "cancel-import", "Cancel restore");
    const resetConfirm = button(confirmation, "confirm-reset", "Start new notebook"), resetCancel = button(confirmation, "cancel-reset", "Keep current notebook");
    content.hidden = false;
    return { view, count, inclusions, activityLimit: 20, element, content, status, selected: session.scope.id, target, note, bookmark, notes, bookmarks, activity, historyStatus, resume, recover, download, conflicts, confirmation, confirmationText, importConfirm, importCancel, resetConfirm, resetCancel };
  }

  const definitions = all<HTMLElement>("[data-av-notebook]").map(element => ({ element, ...prepare(element) }));
  const scopeRoots = new Set<HTMLElement>();
  for (const definition of Array.from(document.querySelectorAll<HTMLElement>("[data-av-notebook]"))) {
    const scope = document.getElementById(definition.getAttribute("data-av-notebook-scope") || "");
    if (scope && scope.contains(definition)) scopeRoots.add(scope);
  }
  const groups = new Map<HTMLElement, typeof definitions>();
  for (const definition of definitions) {
    const id = definition.element.getAttribute("data-av-notebook-scope") || "";
    const scope = document.getElementById(id);
    if (!scope || !scope.contains(definition.element) || !scope.matches(".av-surface,.av-workspace")) { fail(definition.element, definition.content, definition.status, "This notebook could not find its containing report. The report’s evidence is still available."); continue; }
    const group = groups.get(scope) || []; group.push(definition); groups.set(scope, group);
  }
  const keyOwners = new Map<string, HTMLElement>(), conflictingKeys = new Set<string>();
  for (const [scope, group] of groups) for (const definition of group) {
    const key = definition.element.getAttribute("data-av-notebook-storage-key");
    if (key !== null) { if (keyOwners.has(key) && keyOwners.get(key) !== scope) conflictingKeys.add(key); else keyOwners.set(key, scope); }
  }
  for (const [scope, group] of groups) {
    let preparingRegistry: TargetRegistry | null = null;
    try {
      const metadata = group.map(({ element }) => {
        identifier(element.id); identifier(scope.id);
        const revision = element.getAttribute("data-av-notebook-revision") || "";
        const key = element.getAttribute("data-av-notebook-storage-key");
        const rawLimit = element.getAttribute("data-av-notebook-limit");
        if (rawLimit !== null && !/^(0|[1-9]\d*)$/.test(rawLimit)) throw new Error("The notebook’s activity limit is invalid.");
        const limit = rawLimit === null ? DEFAULT_READER_ACTIVITY_LIMIT : Number(rawLimit);
        if (key === "") throw new Error("The notebook’s storage key is empty.");
        if (key && Array.from(document.querySelectorAll("[data-av-storage-key]")).some(surface => surface.getAttribute("data-av-storage-key") === key)) throw new Error("The notebook and display preferences need different storage keys. No saved data has been changed.");
        return { revision, key, limit };
      });
      if (metadata.some(value => exactJson(value) !== exactJson(metadata[0]))) throw new Error("These notebook panels disagree about their report revision or saving settings. No saved notebook has been changed.");
      const { revision, key, limit } = metadata[0];
      if (key !== null && conflictingKeys.has(key)) throw new Error("Different reports share this notebook’s saving key. Give each report its own key before saving reader records.");
      const owns = (element: HTMLElement): boolean => {
        for (let parent: HTMLElement | null = element; parent && parent !== scope; parent = parent.parentElement) if (scopeRoots.has(parent)) return false;
        return scope.contains(element);
      };
      const registry = createTargetRegistry(scope, revision, [...scopeRoots].filter(other => other !== scope));
      preparingRegistry = registry;
      const candidates = [...registry.targets.values()].map(entry => entry.element).filter(owns);
      const targets = new Map<string, Target>();
      const identityCounts = new Map<string, number>();
      for (const node of Array.from(document.querySelectorAll('[id]'))) identityCounts.set(node.id, (identityCounts.get(node.id) || 0) + 1);
      for (const element of new Set(candidates)) {
        if (targets.has(element.id) || identityCounts.get(element.id) !== 1) throw new Error("Notebook targets need unique IDs. No saved notebook has been changed.");
        targets.set(element.id, { element, label: registry.targets.get(element.id)?.target.label || labelOf(element) });
      }
      distinctLabels(targets, scope);
      const views = new Map<string, Target>();
      for (const element of Array.from(scope.querySelectorAll<HTMLElement>("[data-av-panel]")).filter(owns)) {
        const id = element.getAttribute("data-av-panel")!;
        if (views.has(id)) throw new Error("Notebook views need unique identifiers. No saved notebook has been changed.");
        views.set(id, targets.get(element.id) || { element, label: labelOf(element) });
      }
      distinctLabels(views, scope);
      const routes = new Map<string, Route>();
      for (const element of Array.from(scope.querySelectorAll<HTMLElement>("[data-av-journey-id]")).filter(owns)) {
        const id = element.getAttribute("data-av-journey-id")!;
        let steps: unknown;
        try { steps = JSON.parse(element.getAttribute("data-av-journey-steps") || "null"); } catch { throw new Error("A reading route has invalid steps. No saved notebook has been changed."); }
        if (!Array.isArray(steps) || !steps.length || steps.some(step => typeof step !== "string" || !views.has(step))) throw new Error("A reading route refers to an unavailable view. No saved notebook has been changed.");
        if (routes.has(id) && exactJson(routes.get(id)!.steps) !== exactJson(steps)) throw new Error("A reading route has conflicting definitions. No saved notebook has been changed.");
        routes.set(id, { label: element.getAttribute("data-av-journey-label") || id, steps });
      }
      const context: ReaderContext = { reportId: scope.id, revision, targetIds: [...targets.keys()], viewIds: [...views.keys()], journeyIds: [...routes.keys()], activityLimit: limit };
      const initial = emptyReaderNotebook(context);
      const signature = exactJson([revision, key, limit, [...targets.keys()].sort(), [...views.keys()].sort(), [...routes].map(([id, route]) => [id, route.steps])]);
      const cached = retained.get(scope)?.get(signature);
      let seed: ReaderNotebook | undefined, seedError = '';
      try { const reports = readReviewSeed(document)?.reports; const embedded = reports && Object.prototype.hasOwnProperty.call(reports,scope.id) ? reports[scope.id] : undefined; if (embedded) seed = validateReaderNotebook(embedded, context); }
      catch(error) { seedError = 'The embedded review could not be loaded: ' + (error instanceof Error ? error.message : 'invalid review data'); }
      const notebook = cached?.notebook || seed || initial;
      const session: Session = { registry, seed, seedKey: seed ? fingerprint(exactJson(seed)) : undefined, seedInvalid: !!seedError, epochKnown: cached?.epochKnown || false, scope, context, signature, key, store: null, targets, views, routes, panels: [], state: notebook.state, notebook, drafts: new Map(cached?.drafts), lockedRaw: cached?.lockedRaw ?? null, lockMessage: cached?.lockMessage || "", readBlocked: cached?.readBlocked || false, persistence: cached?.persistence || "Kept in this open report. Export a copy to keep it.", notice: "", pending: null, token: 0, writes: [], work: Promise.resolve(), loading: key !== null, saving: false, changed: false, exportJob: null, initialFocus: document.activeElement, stopped: cached?.stopped || false };
      if(seedError){session.lockedRaw=document.getElementById('av-review-seed')?.textContent||'';session.lockMessage=seedError;session.stopped=true;session.readBlocked=true;}
      if (key !== null) session.store = createOwnedStore(document.defaultView, key, { kind: "notebook", reportId: scope.id, revision }, raw => decodeReaderNotebook(raw, context));
      if(peers.has(scope))throw new Error('This report already has an independently owned notebook controller. Enhance each report once.');
      sessions.set(scope, session); preparingRegistry = null; peers.set(scope,session);
      for (const target of targets.values()) owners.set(target.element, session);
      for (const definition of group) { const panel = build(definition.element, definition.content, definition.status, session); session.panels.push(panel); panels.set(panel.element, { panel, session }); }
      session.reviewUI = attachContextReview(scope, registry, { notify:hooks.notify, notebook: () => session.notebook, change: change => apply(session, change), reveal: hooks.reveal, controls: hooks.controls, status: () => [session.notice, storageMessage(session)].filter(Boolean).join(" "), now, id: editId });
      render(session);
      if (session.store) {
        session.persistence = "Opening saved notebook… Current edits stay in this report."; render(session);
        session.work = initialize(session, cached).catch(() => blocked(session, { status: "unavailable", message: "Browser storage could not be read. Your records remain in this report; export a copy to keep them." })).finally(() => { session.loading = false; render(session); persist(session); });
        initialReads.push(session.work);
      }
    } catch (error) {
      preparingRegistry?.cleanup();
      const partial = sessions.get(scope);
      if(partial){partial.loading=false;partial.stopped=true;partial.store?.close();partial.reviewUI?.cleanup();partial.registry.cleanup();sessions.delete(scope);if(peers.get(scope)===partial)peers.delete(scope);}
      for (const definition of group) fail(definition.element, definition.content, definition.status, error instanceof Error ? error.message : "This notebook could not be opened. The report’s evidence is still available.");
    }
  }
  function locate(target: Element): { panel: Panel; session: Session } | undefined {
    if (cleaned) return undefined;
    const element = target.closest<HTMLElement>("[data-av-notebook]");
    return element ? panels.get(element) : undefined;
  }
  function readFile(session: Session, input: HTMLInputElement): void {
    const file = input.files?.[0];
    if (!file) return;
    const token = ++session.token;
    session.pending = { kind: "reading" }; session.notice = ""; render(session); input.value = "";
    let reading: Promise<string>;
    try { reading = file.text(); } catch { reading = Promise.reject(new Error("The selected file could not be read.")); }
    session.importJob = reading.then(raw => {
      if (cleaned || session.token !== token) return;
      try { const state = importReaderReview(raw, session.context); contextual(state.state, session); session.pending = { kind: "import", state, name: file.name || "selected notebook" }; session.notice = "The file is ready. Choose Replace notebook to use it, or cancel."; }
      catch (error) { session.pending = null; session.notice = "The selected notebook was not restored. " + (error instanceof Error ? error.message : "Its records could not be validated."); }
      render(session);
    }, () => { if (cleaned || session.token !== token) return; session.pending = null; session.notice = "The selected file could not be read. Your notebook has not changed."; render(session); });
  }
  function openEntry(session: Session, tab: 'notes' | 'bookmarks', attribute: string, id: string): void {
    const panel = session.panels[0]; if (!panel || cleaned) return;
    panel.view.locate(tab); panel.element.setAttribute('open', '');
    const locate = () => {
      if (cleaned || !panel.element.hasAttribute('open')) return;
      const target = Array.from(panel.content.querySelectorAll<HTMLElement>('[' + attribute + ']')).find(item => item.getAttribute(attribute) === id);
      if (target) { target.tabIndex = -1; target.focus({ preventScroll: true }); target.scrollIntoView?.({ block: 'nearest' }); }
    };
    // Native details/popover opening is queued by the browser. Focus only after
    // that transition, while retaining the same card and originating report.
    (document.defaultView?.requestAnimationFrame || ((fn: () => void) => setTimeout(fn, 0)))(locate);
  }
  return {
    async whenReady() { await Promise.all(initialReads); },
    searchEntries(scope) {
      const session = sessions.get(scope); if (cleaned || !session) return [];
      const entries: SearchEntry[] = [];
      for (const version of session.notebook.review?.versions || []) {
        if (version.text === null) continue;
        entries.push({ kind: 'notes', label: (version.draft ? 'Draft · ' : '') + anchorLabel(version.anchor), text: version.text + '\n' + anchorEvidence(version.anchor), context: anchorContext(version.anchor), activate: () => openEntry(session, 'notes', 'data-av-note-version', version.id) });
      }
      for (const anchor of session.notebook.review?.bookmarks || []) {
        entries.push({ kind: 'bookmarks', label: anchorLabel(anchor), text: anchorEvidence(anchor), context: anchorContext(anchor), activate: () => openEntry(session, 'bookmarks', 'data-av-review-bookmark', fingerprint(exactJson(anchor))) });
      }
      for (const note of session.state.notes) entries.push({ kind: 'notes', label: 'Earlier note · ' + (session.targets.get(note.targetId)?.label || note.targetId), text: note.text, context: 'Earlier target-only note', activate: () => openEntry(session, 'notes', 'data-av-notebook-target-id', note.targetId) });
      for (const id of session.state.bookmarks) entries.push({ kind: 'bookmarks', label: session.targets.get(id)?.label || id, text: '', context: 'Earlier target-only bookmark', activate: () => openEntry(session, 'bookmarks', 'data-av-notebook-target-id', id) });
      return entries;
    },
    hasReview(figure) { return [...sessions.values()].some(session => session.registry.targets.has(figure.id)); },
    reviewSelection(figure, action, trigger) {
      const session = [...sessions.values()].find(session => session.registry.targets.has(figure.id));
      if (!session) return;
      const selected = document.defaultView?.getSelection?.();
      const anchor = figure.getAttribute('data-av-selection-mode') === 'text'
        ? (selected && !selected.isCollapsed ? session.registry.selection(selected) : null) : session.registry.items(selectedFigureItems(figure));
      if (!anchor) { hooks.notify?.({text:'This selection has no unique evidence attachment. Select a single passage inside one record, or annotate the whole figure using its Note command.',tone:'error',source:figure}); return; }
      if (action === 'note') session.reviewUI?.open(anchor,trigger);
      else {
        const enabled = !(session.notebook.review?.bookmarks || []).some(saved => exactJson(saved) === exactJson(anchor));
        if (apply(session,{type:'review-bookmark',anchor,enabled})) hooks.notify?.({text:enabled?'Selection bookmarked.':'Selection bookmark removed.',tone:'success',source:figure});
      }
    },
    click(target) {
      for (const session of sessions.values()) if (session.reviewUI?.click(target)) return true;
      const found = locate(target), control = target.closest<HTMLElement>("[data-av-notebook-action]");
      if (!found || !control || !found.panel.element.contains(control)) return false;
      const { panel, session } = found, action = control.getAttribute("data-av-notebook-action");
      if ((control as HTMLButtonElement).disabled) return true;
      if(action==='activity-more'||action==='activity-less'){panel.activityLimit=action==='activity-more'?panel.activityLimit+20:20;render(session);return true;}

      try {
        if(action==='remove-legacy-bookmark'){
          const targetId=control.getAttribute('data-av-notebook-target-id');
          if(targetId&&session.targets.has(targetId)&&apply(session,{type:'bookmark',targetId,enabled:false,at:now()})){
            panel.content.querySelector<HTMLElement>('[data-av-notebook-tab="bookmarks"]')?.focus({preventScroll:true});
          }
        } else if (action === "new-annotation") {
          const selected = session.targets.get(panel.selected);
          if (selected) { panel.element.removeAttribute('open'); session.reviewUI?.open(session.registry.anchor(selected.element), control); }
        } else if (action === "bookmark-target") {
          const selected = session.targets.get(panel.selected);
          if (selected) {
            const anchor = session.registry.anchor(selected.element);
            const enabled = !(session.notebook.review?.bookmarks || []).some(value => exactJson(value) === exactJson(anchor));
            if (apply(session, { type: 'review-bookmark', anchor, enabled })) hooks.notify?.({ text: enabled ? 'Bookmark added.' : 'Bookmark removed.', tone: 'success', source: panel.element });
          }
        } else if (action === "save-note" || action === "remove-note") {
          capture(panel, session);
          const text = action === "remove-note" ? "" : panel.note.value;
          if (apply(session, { type: "note", targetId: panel.selected, text, at: now() }, hooks.notify ? "" : text === "" ? "The note was removed." : "Your note is in this notebook.")) {session.drafts.delete(panel.selected);hooks.notify?.({text:text===""?"Note removed.":"Note added to this report.",tone:"success",source:panel.element});}
          render(session);
        } else if (action === "resolve-note") {
          const targetId = control.getAttribute("data-av-notebook-target-id")!, version = session.notebook.noteVersions.find(item => item.id === control.getAttribute("data-av-notebook-version-id") && item.targetId === targetId);
          if (version) { if (apply(session, { type: "note", targetId, text: version.text || "", at: now() }, "Your chosen note version is retained.", noteVersionIds(session.notebook, targetId))) session.drafts.delete(targetId); }
        } else if (action === "download") {hooks.notify?.({text:"Download prepared.",tone:"success",source:panel.element});return true;}
        else if (action === "export") {
          if(session.exportBusy)return true;session.exportBusy=true;
          capture(panel, session); panel.download.hidden = true; session.notice = "Preparing a copy, including drafts and competing note versions…";
          session.exportJob = (async () => {
            await refreshForExport(session,false);
            if (cleaned) return;
            const raw = encodeReaderNotebook(snapshot(session), session.context);
            panel.download.setAttribute("href", "data:application/json;charset=utf-8," + encodeURIComponent(raw)); panel.download.setAttribute("download", session.scope.id + "-notebook.json"); panel.download.hidden = false;
            session.notice = hooks.notify ? "" : "Your copy is ready. Download notebook copy includes current drafts and every unresolved note version.";hooks.notify?.({text:"Notebook copy ready.",tone:"success",source:panel.element});render(session);
          })().catch(() => { const message="The copy could not be prepared. Your records remain in this open report.";session.notice=hooks.notify?"":message;hooks.notify?.({text:message,tone:"error",source:panel.element});render(session); });
          session.exportJob=session.exportJob.finally(()=>{session.exportBusy=false;render(session);});
        } else if (action === "export-report" || action === "export-handoff" || action === "copy-handoff") {
          if(session.exportBusy)return true;session.exportBusy=true;
          capture(panel, session);
          const operation = (async () => {
            await Promise.all((action === "export-report" ? [...peers.values()] : [session]).map(other=>refreshForExport(other)));
            if (cleaned) return;
            const copy = session.reviewUI?.exportNotebook(snapshot(session)) || snapshot(session), brief = session.scope.querySelector('[data-av-report-brief],.av-report-brief'), question = brief ? readableReviewText(brief) : '';
            if (action === "export-report") {
              if([...peers.values()].some(other=>other.seedInvalid))throw new Error('Recover or correct the embedded review before creating a new annotated report. Your current notes remain exportable as notebook data.');
              const reports = {...(readReviewSeed(document)?.reports||{}),...Object.fromEntries([...peers].map(([scope, other]) => [scope.id, other.reviewUI?.exportNotebook(snapshot(other)) || snapshot(other)]))};
              downloadBlob(document, new Blob([annotatedReport(document, reports, now())], { type: 'text/html;charset=utf-8' }), session.scope.id + '-reviewed.html');
            } else {
              const text = reviewHandoff(copy, session.registry, question, labelOf(session.scope));
              if (action === "copy-handoff") {
                const clipboard = document.defaultView?.navigator.clipboard; if (!clipboard?.writeText) throw new Error('Clipboard access is unavailable. Download the handoff instead.'); await clipboard.writeText(text);
              } else downloadBlob(document, new Blob([text], { type: 'text/markdown;charset=utf-8' }), session.scope.id + '-handoff.md');
            }
            session.notice = hooks.notify?'':'Your review copy is ready.';hooks.notify?.({text:action==='copy-handoff'?'Handoff copied.':'Download prepared.',tone:'success',source:panel.element});render(session);
          })().catch(error => { const message=error instanceof Error?error.message:'The review copy could not be prepared.';session.notice=hooks.notify?'':message;hooks.notify?.({text:message,tone:'error',source:panel.element});render(session); });
          session.exportJob = operation.finally(()=>{session.exportBusy=false;render(session);});
        } else if (action === "recover") {
          if (session.lockedRaw !== null) { control.setAttribute("href", "data:application/json;charset=utf-8," + encodeURIComponent(session.lockedRaw)); control.setAttribute("download", session.scope.id + "-original-saved-data.json"); session.notice = "The original saved data is ready to download."; }
        } else if (action === "start-reset") { session.token++; session.pending = { kind: "reset" }; }
        else if (action === "cancel-reset" || action === "cancel-import") { session.token++; session.pending = null; session.notice = "Your current notebook has been kept."; panel.target.focus(); }
        else if (action === "confirm-reset" && session.pending?.kind === "reset") {
          session.token++; session.pending = null; replace(session, emptyReaderNotebook(session.context), "A new notebook is open. Protected earlier data has not been changed.");
          for (const other of session.panels) { other.download.hidden = true; other.download.setAttribute("href", "#"); other.download.removeAttribute("download"); }
          panel.target.focus();
        } else if (action === "confirm-import" && session.pending?.kind === "import") {
          const imported = session.pending.state; session.token++; session.pending = null; replace(session, imported, "The imported notebook is now open."); panel.target.focus();
        } else if (action === "resume") { const saved = place(session); if (saved) { hooks.navigate(session.scope, saved); session.notice = "Returned to your saved place."; } }
        else if (action === "open-view") {
          const viewId = control.getAttribute("data-av-notebook-view-id");
          if (viewId !== null && session.views.has(viewId)) hooks.navigate(session.scope, { viewId, mode: "single", journeyId: session.state.journeyId && session.routes.get(session.state.journeyId)?.steps.includes(viewId) ? session.state.journeyId : null });
        } else if (action === "open-target" || action === "edit-note") {
          const id = control.getAttribute("data-av-notebook-target-id"), destination = id === null ? undefined : session.targets.get(id);
          if (destination && id !== null) {
            if (action === "edit-note") { capture(panel, session); panel.selected = id; render(session); panel.note.closest('.av-notebook-legacy')?.setAttribute('open', ''); panel.note.focus(); }
            else { hooks.reveal(destination.element); apply(session, { type: "activity", action: "return-to", targetId: id, at: now() }); }
          }
        } else return false;
      } catch (error) { session.notice = error instanceof Error ? error.message : "This notebook action could not be completed. Your current records remain available."; }
      render(session); return true;
    },
    change(target) {
      for (const session of sessions.values()) if (session.reviewUI?.change(target)) return true;
      const found = locate(target); if (!found) return false;
      const { panel, session } = found;
      if (target === panel.target) { capture(panel, session); if (session.targets.has(panel.target.value)) panel.selected = panel.target.value; render(session); return true; }
      if (target === panel.bookmark) { apply(session, { type: "bookmark", targetId: panel.selected, enabled: panel.bookmark.checked, at: now() }); return true; }
      if (target.hasAttribute("data-av-notebook-import")) { readFile(session, target as HTMLInputElement); return true; }
      return false;
    },
    input(target) {
      for (const session of sessions.values()) if (session.reviewUI?.input(target)) return true;
      const found = locate(target); if (!found || target !== found.panel.note) return false;
      capture(found.panel, found.session); found.session.notice = found.session.drafts.size ? "You have unsaved notes. Export includes your current drafts." : ""; render(found.session); return true;
    },
    restore(scope) { return cleaned ? null : sessions.has(scope) ? place(sessions.get(scope)!) : null; },
    recordPlace(scope, next) {
      const session = sessions.get(scope);
      if (cleaned || !session || next.viewId === null || (session.state.viewId === next.viewId && session.state.mode === next.mode && session.state.journeyId === next.journeyId)) return;
      for(const panel of session.panels)if(!panel.element.hasAttribute('open')&&!session.drafts.has(panel.selected))panel.selected=session.views.get(next.viewId)?.element.id||scope.id;
      apply(session, { type: "navigate", viewId: next.viewId, mode: next.mode, journeyId: next.journeyId, at: now() });
    },
    recordInspection(target) {
      const session = owners.get(target);
      if (!cleaned && session) {
        for(const panel of session.panels)if(!panel.element.hasAttribute('open')&&!session.drafts.has(panel.selected))panel.selected=target.id;
        apply(session, { type: "activity", action: "inspect", targetId: target.id, at: now() });
      }
    },
    async whenIdle() { for (const session of sessions.values()) { await settled(session); await session.importJob; await session.exportJob; } },
    cleanup() {
      if (cleaned) return;
      for (const session of sessions.values()) session.reviewUI?.cleanup();
      cleaned = true;
      for (const session of sessions.values()) {
        session.token++;
        const active = session.panels.find(panel => panel.note === document.activeElement);
        if (active) capture(active, session);
        const cache = retained.get(session.scope) || new Map<string, Memory>();
        // Retain reader data, never detached panel DOM, registry/controllers, or listeners.
        const memory: Memory = { epochKnown: session.epochKnown, state: session.state, notebook: session.notebook, drafts: new Map(session.drafts), lockedRaw: session.lockedRaw, lockMessage: session.lockMessage, persistence: session.persistence, readBlocked: session.readBlocked, stopped: session.stopped, work: Promise.resolve() };
        memory.work = settled(session).then(() => { memory.epochKnown = session.epochKnown; memory.state = session.state; memory.notebook = session.notebook; memory.lockedRaw = session.lockedRaw; memory.lockMessage = session.lockMessage; memory.persistence = session.persistence; memory.readBlocked = session.readBlocked; memory.stopped = session.stopped; });
        cache.set(session.signature, memory); retained.set(session.scope, cache);
        if (!session.loading && !session.saving) session.store?.close();
      }
      for (const restore of undo.reverse()) restore();
      for (const session of sessions.values()) {session.registry.cleanup();if(peers.get(session.scope)===session)peers.delete(session.scope);}
      panels.clear(); sessions.clear();
    },
  };
}
