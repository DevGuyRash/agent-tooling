/** The collection's reader: #report/ID opens a member's full report in the
 * page, #compare/A/B two members side by side, and any other address returns to
 * the collection. The report index's filters and its compare picker live here
 * too. A member is rendered only while it is open, with its own address space
 * (#report/ID/run-3, #report/ID/runs?outcome=fail), so its drawer, ledger and
 * links behave as in its standalone file. Back, Escape and the reader bar's
 * link return to the collection where the reader left it. */
import { esc } from "./core";
import { collectionModel, compareReport, memberReport, MEMBER_ID } from "./collection";
import type { Collection, MemberSummary } from "./collection";
import type { ReportSpec } from "./model";

type MountInner = (host: HTMLElement, spec: ReportSpec, hashBase: string) => { cleanup(): void };
type Route = { kind: "report"; id: string; base: string } | { kind: "compare"; a: string; b: string; base: string };
const FIELDS = "input, select, textarea, [contenteditable=''], [contenteditable='true']";
/** The element with an id inside one report: a member and the collection both have ids such as av-top. */
function byId(root: ParentNode | null, id: string): HTMLElement | null {
  if (!root || !id) return null;
  try { return root.querySelector<HTMLElement>(`[id="${id.replace(/["\\]/g, "\\$&")}"]`); } catch { return null; }
}

/** A reader address, or null for any other address. */
export function readerRoute(raw: string): Route | null {
  const h = raw.replace(/^#/, "");
  const decode = (s: string) => { try { return decodeURIComponent(s); } catch { return s; } };
  const r = /^report\/([^/?#]+)(?:\/.*)?$/.exec(h);
  if (r && MEMBER_ID.test(decode(r[1]))) return { kind: "report", id: decode(r[1]), base: `#report/${r[1]}` };
  const c = /^compare\/([^/?#]+)\/([^/?#]+)(?:\/.*)?$/.exec(h);
  if (c && MEMBER_ID.test(decode(c[1])) && MEMBER_ID.test(decode(c[2]))) return { kind: "compare", a: decode(c[1]), b: decode(c[2]), base: `#compare/${c[1]}/${c[2]}` };
  return null;
}

export function attachReader(target: HTMLElement, data: Collection, mountInner: MountInner): { start(): void; cleanup(): void } {
  const doc = target.ownerDocument, win = doc.defaultView!;
  const loc = win.location, hist = win.history;
  const home = target.querySelector<HTMLElement>("[data-av-report]");
  const model = collectionModel(data);
  const offs: Array<() => void> = [];
  const on = (el: EventTarget | null | undefined, type: string, fn: (e: any) => void) => {
    if (!el || typeof el.addEventListener !== "function") return;
    el.addEventListener(type, fn); offs.push(() => el.removeEventListener(type, fn));
  };
  const titleBefore = doc.title;
  let view: { key: string; base: string; host: HTMLElement; inner: { cleanup(): void } } | null = null;
  let back = { hash: "#av-top", scroll: 0, focus: null as Element | null };
  // The collection address the reader last saw, where Back and Escape return.
  let currentHomeHash = "";

  // ---------------------------------------------------------------- the index's filters and picker
  for (const rx of home ? Array.from(home.querySelectorAll<HTMLElement>("[data-av-rx]")) : []) {
    const tools = rx.querySelector<HTMLElement>("[data-av-rx-tools]"), tray = rx.querySelector<HTMLElement>("[data-av-rx-tray]");
    const cards = Array.from(rx.querySelectorAll<HTMLElement>("[data-av-rx-card]"));
    const groups = Array.from(rx.querySelectorAll<HTMLElement>("[data-av-rx-group]"));
    const count = rx.querySelector<HTMLElement>("[data-av-rx-count]"), none = rx.querySelector<HTMLElement>("[data-av-rx-none]");
    const clear = rx.querySelector<HTMLButtonElement>("[data-av-rx-clear]");
    const theme = rx.querySelector<HTMLSelectElement>("[data-av-rx-theme]"), modelSel = rx.querySelector<HTMLSelectElement>("[data-av-rx-model]"), q = rx.querySelector<HTMLInputElement>("[data-av-rx-q]");
    const chips = Array.from(rx.querySelectorAll<HTMLButtonElement>("[data-av-rx-verdict]"));
    let verdict = "";
    if (tools) tools.hidden = false;
    // Every index design lists the same reports, so one filter narrows them all; counts are of reports, not entries.
    const total = new Set(cards.map(c => c.dataset.member)).size;
    const apply = () => {
      const text = (q?.value || "").trim().toLowerCase(), words = text.split(/\s+/).filter(Boolean);
      const kept = new Set<string>();
      for (const c of cards) {
        const ok = (!verdict || c.dataset.verdict === verdict) && (!theme?.value || c.dataset.theme === theme.value)
          && (!modelSel?.value || (c.dataset.models || "").split("\n").includes(modelSel.value)) && words.every(w => (c.dataset.search || "").includes(w));
        c.hidden = !ok; if (ok) kept.add(c.dataset.member || "");
      }
      const shown = kept.size;
      for (const g of groups) g.hidden = !g.querySelector("[data-av-rx-card]:not([hidden])");
      for (const chip of chips) chip.setAttribute("aria-pressed", String(chip.dataset.avRxVerdict === verdict));
      const filtered = !!(verdict || theme?.value || modelSel?.value || text);
      if (count) count.textContent = filtered ? `${shown} of ${total} reports` : `${total} reports`;
      if (none) none.hidden = shown > 0;
      if (clear) clear.hidden = !filtered;
    };
    for (const chip of chips) on(chip, "click", () => { verdict = chip.dataset.avRxVerdict || ""; apply(); });
    on(theme, "change", apply); on(modelSel, "change", apply); on(q, "input", apply);
    on(clear, "click", () => { verdict = ""; if (theme) theme.value = ""; if (modelSel) modelSel.value = ""; if (q) q.value = ""; apply(); (chips[0] || q)?.focus(); });
    // Picking two reports to compare: a third pick replaces the older one.
    const picks: string[] = [];
    const pickButtons = Array.from(rx.querySelectorAll<HTMLButtonElement>("[data-av-rx-pick]"));
    const go = rx.querySelector<HTMLAnchorElement>("[data-av-rx-go]"), said = rx.querySelector<HTMLElement>("[data-av-rx-picked]");
    const name = (id: string) => model.byId.get(id)?.short || id;
    const sync = () => {
      for (const b of pickButtons) b.setAttribute("aria-pressed", String(picks.includes(b.dataset.avRxPick || "")));
      if (tray) tray.hidden = !picks.length;
      if (said) said.textContent = picks.length === 2 ? `A: ${name(picks[0])} · B: ${name(picks[1])}` : picks.length ? `A: ${name(picks[0])}. Pick one more report to compare with it.` : "";
      if (go) {
        if (picks.length === 2) { go.href = `#compare/${encodeURIComponent(picks[0])}/${encodeURIComponent(picks[1])}`; go.removeAttribute("aria-disabled"); }
        else { go.href = "#"; go.setAttribute("aria-disabled", "true"); }
      }
    };
    for (const b of pickButtons) {
      b.hidden = false;
      on(b, "click", () => {
        const id = b.dataset.avRxPick || "", at = picks.indexOf(id);
        if (at >= 0) picks.splice(at, 1); else { picks.push(id); if (picks.length > 2) picks.shift(); }
        sync();
      });
    }
    on(go, "click", (e: MouseEvent) => { if (picks.length < 2) e.preventDefault(); });
    on(rx.querySelector("[data-av-rx-unpick]"), "click", () => { picks.splice(0); sync(); pickButtons.find(b => b.offsetParent !== null)?.focus(); });
    // Index designs: one shows at a time.
    const layoutButtons = Array.from(rx.querySelectorAll<HTMLButtonElement>("[data-av-rx-layout]"));
    for (const b of layoutButtons) on(b, "click", () => {
      for (const x of layoutButtons) x.setAttribute("aria-pressed", String(x === b));
      for (const v of Array.from(rx.querySelectorAll<HTMLElement>("[data-av-rx-view]"))) v.hidden = v.dataset.avRxView !== b.dataset.avRxLayout;
    });
    // The table sorts by any column; a second press reverses it.
    for (const table of Array.from(rx.querySelectorAll<HTMLTableElement>("table.av-rx-table"))) {
      const heads = Array.from(table.querySelectorAll<HTMLTableCellElement>("th[data-av-rx-sortable]"));
      heads.forEach((th, col) => on(th.querySelector("button"), "click", () => {
        const dir = th.getAttribute("aria-sort") === "ascending" ? -1 : 1, numeric = th.dataset.avRxSortable === "number";
        for (const h of heads) h.removeAttribute("aria-sort");
        th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
        const body = table.tBodies[0], rows = Array.from(body.rows);
        const value = (r: HTMLTableRowElement) => r.cells[col]?.dataset.v ?? "";
        rows.sort((a, b) => { const x = value(a), y = value(b); return dir * (numeric ? Number(x) - Number(y) : x < y ? -1 : x > y ? 1 : 0); });
        for (const r of rows) body.appendChild(r);
      }));
    }
    apply();
  }

  // ---------------------------------------------------------------- the reader
  const where = (s: MemberSummary) => model.themes.find(t => t.members.includes(s))?.label || "";
  const options = (current: string) => model.themes.map(t => `<optgroup label="${esc(t.label)}">${t.members.filter(s => s.id !== current).map(s => `<option value="${esc(s.id)}">${esc(s.short)}</option>`).join("")}</optgroup>`).join("");
  const bar = (r: Route): string => {
    const backLink = `<a class="av-reader-back" href="${esc(back.hash)}" data-av-reader-back><span aria-hidden="true">←</span> All reports</a>`;
    if (r.kind === "compare") {
      const a = model.byId.get(r.a), b = model.byId.get(r.b);
      return `<nav class="av-reader-bar" aria-label="Collection">${backLink}<span class="av-reader-where">Side by side</span><span class="av-reader-actions">${a && b ? `<a class="av-btn av-btn--small" href="#compare/${encodeURIComponent(r.b)}/${encodeURIComponent(r.a)}">Swap A and B</a>` : ""}${a ? `<a class="av-btn av-btn--small" href="#report/${encodeURIComponent(r.a)}">Read A</a>` : ""}${b ? `<a class="av-btn av-btn--small" href="#report/${encodeURIComponent(r.b)}">Read B</a>` : ""}</span></nav>`;
    }
    const s = model.byId.get(r.id)!, list = model.themes.flatMap(t => t.members), at = list.indexOf(s);
    const prev = list[at - 1], next = list[at + 1];
    return `<nav class="av-reader-bar" aria-label="Collection">${backLink}<span class="av-reader-where">${esc(where(s))}<span class="av-muted"> · report ${at + 1} of ${list.length}</span></span><span class="av-reader-actions">${prev ? `<a class="av-btn av-btn--small" rel="prev" href="#report/${encodeURIComponent(prev.id)}" title="${esc(prev.short)}"><span aria-hidden="true">← </span>Previous</a>` : ""}${next ? `<a class="av-btn av-btn--small" rel="next" href="#report/${encodeURIComponent(next.id)}" title="${esc(next.short)}">Next<span aria-hidden="true"> →</span></a>` : ""}${list.length > 1 ? `<label class="av-reader-compare"><span>Compare with</span><select data-av-reader-compare><option value="">another report…</option>${options(s.id)}</select></label>` : ""}</span></nav>`;
  };
  const missing = (ids: string[]): ReportSpec => ({
    title: "Not in this collection", kicker: "Collection", problems: [],
    sections: [{ id: "missing", title: "No such report", blocks: [{ type: "text", text: `This collection has no report with the id ${ids.map(id => `\`${id}\``).join(" or ")}. Its reports: ${model.members.map(s => `\`${s.id}\``).join(", ") || "none"}.` }] }],
  });
  const closeView = () => {
    if (!view) return;
    view.inner.cleanup(); view.host.remove(); view = null;
    if (home) home.hidden = false;
    doc.title = titleBefore;
  };
  const show = (key: string, r: Route, spec: ReportSpec, title: string, inner: boolean) => {
    if (view?.key === key) return;
    if (!view) back = { hash: currentHomeHash || "#av-top", scroll: win.scrollY || 0, focus: doc.activeElement };
    closeView();
    const host = doc.createElement("div");
    host.className = "av-reader"; host.setAttribute("data-av-reader", key);
    host.innerHTML = bar(r);
    const body = doc.createElement("div");
    body.className = "av-reader-body"; host.appendChild(body);
    target.appendChild(host);
    if (home) home.hidden = true;
    view = { key, base: r.base, host, inner: mountInner(body, spec, r.base) };
    doc.title = title;
    // A back link in the report's own sticky bar keeps the way home in reach while reading.
    const topbar = body.querySelector(".av-topbar-inner");
    if (topbar) topbar.insertAdjacentHTML("afterbegin", `<a class="av-reader-topback" href="${esc(back.hash)}" aria-label="All reports" data-av-reader-back><span aria-hidden="true">←</span></a>`);
    // A link inside the open report (its section index, its brand, an alert's link) stays inside it: it is followed under
    // the report's own address, even when the collection behind it has an element with the same id (both have av-top).
    on(host, "click", (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.<HTMLAnchorElement>("a[href^='#']");
      if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.hasAttribute("data-av-reader-back")) return;
      const href = a.getAttribute("href") || "";
      if (readerRoute(href)) return;
      let id = href.slice(1).split("?")[0];
      try { id = decodeURIComponent(id); } catch { /* keep it raw */ }
      const inside = byId(body, id);
      if (!inside) return;
      e.preventDefault();
      loc.hash = `${r.base}/${href.slice(1)}`;
      inside.scrollIntoView?.({ block: "start" });
    });
    on(host.querySelector("[data-av-reader-compare]"), "change", (e: Event) => {
      const v = (e.target as HTMLSelectElement).value;
      if (v && r.kind === "report") loc.hash = `#compare/${encodeURIComponent(r.id)}/${encodeURIComponent(v)}`;
    });
    if (!inner) {
      win.scrollTo?.({ top: 0, left: 0, behavior: "instant" as ScrollBehavior });
      const h1 = body.querySelector<HTMLElement>(".av-title");
      if (h1) { h1.setAttribute("tabindex", "-1"); try { h1.focus({ preventScroll: true }); } catch { h1.focus(); } }
    }
  };
  const route = () => {
    const raw = loc.hash || "";
    const r = readerRoute(raw);
    const inner = !!r && raw.length > r.base.length;
    if (r?.kind === "report") {
      const spec = model.byId.has(r.id) ? memberReport(data, r.id) : null;
      show(`report:${r.id}`, r, spec || missing([r.id]), spec ? `${model.byId.get(r.id)!.short} · ${titleBefore}` : titleBefore, inner);
      return;
    }
    if (r?.kind === "compare") {
      const ok = model.byId.has(r.a) && model.byId.has(r.b) && r.a !== r.b;
      show(`compare:${r.a}/${r.b}`, r, ok ? compareReport(data, r.a, r.b) : missing([r.a, r.b].filter(id => !model.byId.has(id))), ok ? `${model.byId.get(r.a)!.short} and ${model.byId.get(r.b)!.short} · ${titleBefore}` : titleBefore, inner);
      return;
    }
    let id = raw.replace(/^#/, "").split("?")[0];
    try { id = decodeURIComponent(id); } catch { /* keep it raw */ }
    const el = byId(home, id);
    if (view) {
      // Links inside the open report were rewritten to its own address when followed, so any other address leaves it.
      const returning = raw === back.hash || !el;
      closeView();
      if (returning) {
        // Again after the collection's own handling of the address (which marks a section it names), so the reader
        // lands where it left, on what opened the report.
        const { scroll, focus } = back;
        const restore = () => {
          win.scrollTo?.({ top: scroll, left: 0, behavior: "instant" as ScrollBehavior });
          const f = focus as HTMLElement | null;
          if (f && f.isConnected && typeof f.focus === "function") { try { f.focus({ preventScroll: true }); } catch { f.focus(); } }
        };
        restore();
        if (typeof win.setTimeout === "function") win.setTimeout(restore, 0);
      } else if (el) el.scrollIntoView?.({ block: "start" });
    }
    currentHomeHash = raw;
  };
  on(win, "hashchange", route);
  on(doc, "keydown", (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !view || e.altKey || e.ctrlKey || e.metaKey) return;
    if (doc.querySelector("dialog[open]") || (e.target as Element | null)?.closest?.(FIELDS)) return;
    e.preventDefault();
    loc.hash = back.hash;
  });
  return {
    start() { route(); },
    cleanup() { offs.splice(0).forEach(f => f()); closeView(); },
  };
}
