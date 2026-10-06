/** Browser behavior for a rendered report: theme, section index, deep links,
 * the run drawer, ledger filtering, sorting and export, keyboard movement
 * between run marks, tooltips, announcements, printing and diagrams. Every view
 * is complete without it; this only adds ways to move through the data. Each
 * browser feature is used only where present, so a partial document (or a test
 * double) gets the behaviors it can support and never an error. */
import { esc, fmtNum, fmtSeconds, inline, isNum, outcomeBadge, outcomeLabel, outcomeMark } from "./core";
import { failureCause, invalidReason } from "./failure";
import { attachMermaid, DiagramController } from "./mermaid";
import { createContext, RenderContext, ReportSpec } from "./model";
import { renderReport } from "./report";
import { displayPath, judgeQuestion, outcomeOf, recordPath, TrialReport, TrialRun, TrialScenario } from "./trial-model";

const THEME_KEY = "av-theme";
const themes = ["auto", "light", "dark"] as const;
type Theme = typeof themes[number];

function storedTheme(): Theme {
  try { const v = globalThis.localStorage?.getItem(THEME_KEY); return (themes as readonly string[]).includes(v || "") ? v as Theme : "auto"; } catch { return "auto"; }
}
function applyTheme(doc: Document, theme: Theme): void {
  if (theme === "auto") doc.documentElement.removeAttribute("data-theme"); else doc.documentElement.setAttribute("data-theme", theme);
  try { if (theme === "auto") globalThis.localStorage?.removeItem(THEME_KEY); else globalThis.localStorage?.setItem(THEME_KEY, theme); } catch { /* storage may be unavailable */ }
}

// ------------------------------------------------------------------ export

/** One CSV field (RFC 4180). Text that a spreadsheet would run as a formula
 * (starting with =, +, -, @, tab or carriage return) gets a leading apostrophe;
 * numbers and booleans are written as themselves. */
export function csvCell(value: unknown): string {
  let text: string;
  if (value === null || value === undefined) text = "";
  else if (typeof value === "number") text = Number.isFinite(value) ? String(value) : "";
  else if (typeof value === "boolean") text = value ? "true" : "false";
  else {
    if (typeof value === "string") text = value;
    else { try { text = JSON.stringify(value) ?? ""; } catch { text = ""; } }
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
  }
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

const scenarioOf = (data: TrialReport, run: TrialRun): TrialScenario | undefined =>
  (Array.isArray(data.plan?.scenarios) ? data.plan!.scenarios : []).find(s => !!s && s.name === run.scenario);

/** The given runs (indexes into data.runs, in that order) as CSV: one row per
 * run with its outcome, cause, judge, timing and usage, then one column per
 * recorded check. Labels default to the raw ids. */
export function runsCsv(data: TrialReport, indexes?: number[], labels: { arm?: (id: string) => string; case?: (id: string) => string } = {}): string {
  const runs = Array.isArray(data?.runs) ? data.runs : [];
  const picked = (indexes || runs.map((_, i) => i)).filter(i => Number.isInteger(i) && !!runs[i]);
  const checkNames: string[] = [];
  const seen = new Set<string>();
  for (const i of picked) for (const k of Object.keys(runs[i].checks && typeof runs[i].checks === "object" ? runs[i].checks! : {})) if (!seen.has(k)) { seen.add(k); checkNames.push(k); }
  const usage = (r: TrialRun, k: string) => { const v = r.usage && typeof r.usage === "object" ? r.usage[k] : undefined; return isNum(v) ? v : null; };
  const head = ["n", "job", "case", "case_label", "arm", "arm_label", "repeat", "outcome", "cause", "invalid_reason", "judge_verdict", "judge_reason",
    "seconds", "output_tokens", "input_tokens", "total_cost_usd", "commands", "record_path", ...checkNames.map(k => `check.${k}`)];
  const lines = [head.map(csvCell).join(",")];
  for (const i of picked) {
    const r = runs[i], o = outcomeOf(r);
    let cause = "";
    try { cause = failureCause(r, scenarioOf(data, r)).text; } catch { cause = ""; }
    const scenario = String(r.scenario ?? ""), arm = String(r.arm ?? "");
    lines.push([
      i + 1, r.job ?? "", scenario, labels.case ? labels.case(scenario) : scenario, arm, labels.arm ? labels.arm(arm) : arm,
      isNum(r.repeat) ? r.repeat : "", o, cause, o === "invalid" ? (r.invalid_reason || r.status || "") : "",
      r.judge?.verdict ?? "", r.judge?.reason ?? "", isNum(r.seconds) ? r.seconds : "", usage(r, "output_tokens"), usage(r, "input_tokens"),
      usage(r, "total_cost_usd"), isNum(r.commands) ? r.commands : "", recordPath(data, r) ?? "",
      ...checkNames.map(k => r.checks && Object.prototype.hasOwnProperty.call(r.checks, k) ? r.checks[k] : null),
    ].map(csvCell).join(","));
  }
  return lines.join("\r\n") + "\r\n";
}

/** A file name from a trial name: lowercase letters, digits and hyphens. */
function fileStem(name: unknown): string {
  return String(name || "trial").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "trial";
}

// ------------------------------------------------------------------ enhance

export interface Enhancement { cleanup(): void; diagrams?: DiagramController }

/** Ids for elements this adds, unique across every report on a page. */
let ledgerSeq = 0;
const MARKS = "button[data-run]";
const TIPPED = "button[data-run], [data-av-tip]";
const FIELDS = "input, select, textarea, [contenteditable=''], [contenteditable='true']";

/** Add behavior to a rendered report. `ctx` supplies the trial runs for the drawer. */
export function enhance(root: HTMLElement, ctx?: RenderContext): Enhancement {
  const doc = root.ownerDocument, win = doc.defaultView!;
  const report = root.matches("[data-av-report]") ? root : root.querySelector<HTMLElement>("[data-av-report]") || root;
  const offs: Array<() => void> = [];
  const on = (el: EventTarget | null | undefined, type: string, fn: (e: any) => void, opts?: AddEventListenerOptions) => {
    if (!el || typeof el.addEventListener !== "function") return;
    el.addEventListener(type, fn, opts); offs.push(() => el.removeEventListener(type, fn, opts));
  };
  const timers = new Set<number>();
  const later = (fn: () => void, ms: number) => {
    if (typeof win.setTimeout !== "function") { fn(); return; }
    const id = win.setTimeout(() => { timers.delete(id); fn(); }, ms); timers.add(id);
  };
  // Everything this adds to the page is removed again by cleanup().
  const added: Element[] = [];
  const make = (tag: string, attributes: Record<string, string> = {}, text?: string): HTMLElement | null => {
    if (typeof doc.createElement !== "function") return null;
    const el = doc.createElement(tag);
    added.push(el);
    for (const [k, v] of Object.entries(attributes)) el.setAttribute(k, v);
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const all = <E extends Element = HTMLElement>(selector: string, scope: ParentNode = report): E[] => Array.from(scope.querySelectorAll<E>(selector));
  /** The phone layout (styles/components.css, max-width 640px), where ledger rows are cards. */
  const narrow = () => { try { return !!win.matchMedia?.("(max-width: 640px)").matches; } catch { return false; } };
  const data = ctx?.trial;
  const dialog = report.querySelector<HTMLDialogElement>("[data-av-drawer]");
  const loc = win.location, hist = win.history;
  let diagrams: DiagramController | undefined;

  // Announcements: one polite region for the page and one inside the drawer,
  // since a modal dialog hides everything outside it from assistive technology.
  const liveRegion = (parent: Element | null) => {
    const el = make("div", { class: "av-sr", "aria-live": "polite", "aria-atomic": "true", "data-av-live": "" });
    if (el && parent && typeof parent.appendChild === "function") parent.appendChild(el);
    return el && parent ? el : null;
  };
  const pageLive = liveRegion(report), drawerLive = liveRegion(dialog);
  const announce = (text: string, region: HTMLElement | null = dialog?.open ? drawerLive : pageLive) => {
    if (!region) return;
    region.textContent = "";
    later(() => { region.textContent = text; }, 60);
  };

  // Copying: the clipboard where the viewer allows it, else a selection the
  // reader can copy by hand. Resolves to whether the text reached the clipboard.
  const copyText = async (text: string, near: Element | null): Promise<boolean> => {
    try { if (win.navigator?.clipboard?.writeText) { await win.navigator.clipboard.writeText(text); return true; } } catch { /* refused: try the older route */ }
    const area = make("textarea", { readonly: "", class: "av-sr", "aria-hidden": "true", tabindex: "-1" }) as HTMLTextAreaElement | null;
    const host = near?.closest("dialog") || report;
    if (!area) return false;
    area.value = text; host.appendChild(area);
    let ok = false;
    try { area.select(); ok = doc.execCommand("copy"); } catch { ok = false; }
    area.remove();
    return ok;
  };
  const flash = (button: HTMLElement, text: string) => {
    const word = button.querySelector<HTMLElement>("[data-av-word]") || button;
    const before = word.dataset.avRest ?? word.textContent ?? "";
    word.dataset.avRest = before; word.textContent = text;
    later(() => { if (word.isConnected) word.textContent = before; delete word.dataset.avRest; }, 1800);
  };
  const selectText = (el: Element | null) => {
    try { if (!el || !win.getSelection) return; const range = doc.createRange(); range.selectNodeContents(el); const sel = win.getSelection()!; sel.removeAllRanges(); sel.addRange(range); } catch { /* selection unavailable */ }
  };

  // Downloads through a Blob link; viewers that block downloads get a message
  // naming the alternative instead of silence.
  const download = (name: string, text: string, type: string): boolean => {
    try {
      const blob = new win.Blob([text], { type });
      const url = win.URL.createObjectURL(blob);
      const a = make("a", { href: url, download: name, rel: "noopener", hidden: "" });
      if (!a) return false;
      report.appendChild(a); a.click(); a.remove();
      later(() => { try { win.URL.revokeObjectURL(url); } catch { /* already gone */ } }, 60000);
      return true;
    } catch { return false; }
  };

  // Hash: run links (#run-12), section links (#cost) and ledger views
  // (#runs?outcome=fail&arm=…). replaceState never fires hashchange.
  const currentHash = () => loc?.hash || "";
  const setHash = (hash: string) => {
    try { if (hist?.replaceState && loc) hist.replaceState(hist.state, "", hash || loc.pathname + loc.search); } catch { /* sandboxed viewers may refuse */ }
  };
  const linkTo = (hash: string) => loc ? loc.href.replace(/#.*$/, "") + hash : hash;

  // Theme -------------------------------------------------------------
  const toggle = report.querySelector<HTMLButtonElement>("[data-av-theme-toggle]");
  if (toggle) {
    const show = (t: Theme) => { toggle.setAttribute("data-theme-choice", t); toggle.querySelector(".av-theme-word")!.textContent = t === "auto" ? "Auto" : t === "light" ? "Light" : "Dark"; toggle.setAttribute("aria-label", `Color theme: ${t === "auto" ? "follows the system" : t}. Select to change.`); };
    show(storedTheme()); toggle.hidden = false;
    on(toggle, "click", () => { const next = themes[(themes.indexOf(storedTheme()) + 1) % themes.length]; applyTheme(doc, next); show(next); diagrams?.refresh(); });
  }

  // Section index: the current section is the last whose top has passed a
  // line a third of the way down the window; above the first, none is current.
  const links = all<HTMLAnchorElement>(".av-toc a");
  const sections = links.map(a => doc.getElementById(decodeURIComponent(a.hash.slice(1)))).filter((s): s is HTMLElement => !!s);
  const bar = report.querySelector<HTMLElement>(".av-topbar");
  let spyQueued = false;
  const spy = () => {
    spyQueued = false;
    const line = win.innerHeight * 0.33;
    let current: HTMLElement | undefined;
    for (const s of sections) if (s.getBoundingClientRect().top <= line) current = s;
    for (const a of links) {
      const active = !!current && a.hash === "#" + current.id;
      if (active !== a.hasAttribute("aria-current")) { a.toggleAttribute("aria-current", active); if (active) a.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }
    }
    bar?.toggleAttribute("data-scrolled", win.scrollY > 8);
  };
  const queue = () => { if (!spyQueued) { spyQueued = true; win.requestAnimationFrame ? win.requestAnimationFrame(spy) : spy(); } };
  on(win, "scroll", queue, { passive: true }); on(win, "resize", queue);
  if (links.length || bar) spy();

  // A second skip link straight to the ledger, the record of every run.
  const ledgerSection = report.querySelector<HTMLTableElement>("table.av-ledger")?.closest<HTMLElement>(".av-section[id]");
  const firstSkip = report.querySelector<HTMLAnchorElement>(".av-skip");
  if (ledgerSection && firstSkip && !report.querySelector("[data-av-skip-ledger]")) {
    const skip = make("a", { class: "av-skip", href: `#${ledgerSection.id}`, "data-av-skip-ledger": "" }, "Skip to the run ledger");
    if (skip) firstSkip.after(skip);
  }

  // Section links: a control in each section head copies a link to it.
  for (const section of all(".av-section[id]")) {
    const head = section.querySelector<HTMLElement>(".av-section-head");
    if (!head) continue;
    let anchor = head.querySelector<HTMLAnchorElement>(".av-anchor");
    if (!anchor) {
      const title = section.querySelector(".av-section-title")?.textContent?.trim() || section.id;
      anchor = make("a", { class: "av-anchor", href: `#${section.id}`, "aria-label": `Copy a link to this section: ${title}` }) as HTMLAnchorElement | null;
      if (!anchor) continue;
      const mark = make("span", { "aria-hidden": "true", class: "av-anchor-mark" }, "#"), word = make("span", { class: "av-anchor-word", "data-av-word": "" }, "Link");
      if (mark && word) anchor.append(mark, word);
      head.appendChild(anchor);
    }
    const a = anchor;
    on(a, "click", async (e: MouseEvent) => {
      if (e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      const hash = `#${section.id}`;
      if (!dialog?.open) setHash(hash);
      const copied = await copyText(linkTo(hash), a);
      flash(a, copied ? "Copied" : "In address bar");
      announce(copied ? "Link to this section copied." : "Copying is blocked here; the address bar now holds the link to this section.", pageLive);
    });
  }

  // Wide content: fade the edge that has more to scroll to, so a clipped table
  // or grid announces that it continues.
  const scrollers = all(".av-scroll-x, .av-plot-scroll");
  const edge = (el: HTMLElement) => {
    const x = el.scrollWidth - el.clientWidth > 2, y = el.scrollHeight - el.clientHeight > 2;
    el.toggleAttribute("data-more-right", x && el.scrollLeft < el.scrollWidth - el.clientWidth - 2);
    el.toggleAttribute("data-more-left", x && el.scrollLeft > 2);
    el.toggleAttribute("data-more-down", y && el.scrollTop < el.scrollHeight - el.clientHeight - 2);
  };
  for (const el of scrollers) { on(el, "scroll", () => edge(el), { passive: true }); edge(el); }
  on(win, "resize", () => scrollers.forEach(edge));
  // Content that arrives later (a diagram drawn after mount) re-measures its scroller.
  let sizes: ResizeObserver | undefined, children: MutationObserver | undefined;
  if (typeof win.ResizeObserver === "function" && typeof win.MutationObserver === "function") {
    const scrollerOf = (el: Element) => el.matches(".av-scroll-x, .av-plot-scroll") ? el as HTMLElement : el.parentElement?.closest<HTMLElement>(".av-scroll-x, .av-plot-scroll");
    sizes = new win.ResizeObserver(entries => { for (const e of entries) { const sc = scrollerOf(e.target); if (sc) edge(sc); } });
    children = new win.MutationObserver(records => { for (const r of records) { const sc = r.target as HTMLElement; for (const n of Array.from(r.addedNodes)) if (n instanceof win.Element) sizes!.observe(n); edge(sc); } });
    for (const el of scrollers) { sizes.observe(el); if (el.firstElementChild) sizes.observe(el.firstElementChild); children.observe(el, { childList: true }); }
  }

  // Arm highlight -------------------------------------------------------
  on(report, "pointerover", (e: PointerEvent) => {
    const tag = (e.target as Element).closest?.(".av-arm[data-arm]");
    const block = tag?.closest(".av-block");
    if (!tag || !block) return;
    const arm = tag.getAttribute("data-arm");
    block.classList.add("av-has-hl");
    block.querySelectorAll("[data-arm]").forEach(el => el.classList.toggle("av-hl-on", el.getAttribute("data-arm") === arm));
  });
  on(report, "pointerout", (e: PointerEvent) => {
    const tag = (e.target as Element).closest?.(".av-arm[data-arm]");
    if (!tag || (e.relatedTarget as Element | null)?.closest?.(".av-arm[data-arm]") === tag) return;
    const block = tag.closest(".av-block");
    block?.classList.remove("av-has-hl");
    block?.querySelectorAll(".av-hl-on").forEach(el => el.classList.remove("av-hl-on"));
  });

  // Run grid: each cell carries a copy of its column's heading, which narrow
  // screens show when the grid becomes a list (case, then one line per arm).
  // Hidden from assistive technology: the column header already names it.
  for (const grid of all(".av-tap")) {
    const heads = all(".av-tap-row--head .av-tap-colhead", grid);
    if (!heads.length) continue;
    for (const row of all(".av-tap-row", grid)) {
      if (row.matches(".av-tap-row--head, .av-tap-row--group")) continue;
      Array.from(row.children).filter(c => c.matches(".av-tap-cell")).forEach((cell, i) => {
        if (!heads[i] || cell.querySelector(".av-tap-cell-arm")) return;
        const label = make("span", { class: "av-tap-cell-arm", "aria-hidden": "true" });
        if (!label) return;
        for (const child of Array.from(heads[i].childNodes)) label.appendChild(child.cloneNode(true));
        cell.insertBefore(label, cell.firstChild);
      });
    }
  }

  // Tooltips: run marks show their accessible name at once, in the report's
  // own style. The native title would repeat it late, so it moves to aria-label.
  const tip = make("div", { class: "av-tip", "aria-hidden": "true" });
  if (tip) report.appendChild(tip);
  let tipFor: Element | null = null;
  for (const el of all(`${MARKS}[title]`)) { if (!el.getAttribute("aria-label")) el.setAttribute("aria-label", el.title); el.removeAttribute("title"); }
  const hideTip = () => { if (tip && tipFor) { tip.removeAttribute("data-show"); tipFor = null; } };
  const showTip = (el: HTMLElement) => {
    if (!tip || dialog?.open) return;
    const text = el.getAttribute("data-av-tip") || el.getAttribute("aria-label") || "";
    if (!text) { hideTip(); return; }
    tipFor = el; tip.textContent = text;
    tip.setAttribute("data-show", "");
    const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect(), vw = doc.documentElement.clientWidth || win.innerWidth;
    const cx = r.left + r.width / 2, top = bar ? bar.getBoundingClientRect().bottom : 0;
    const left = Math.max(8, Math.min(vw - t.width - 8, cx - t.width / 2));
    const above = r.top - t.height - 10 >= top + 4;
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(above ? r.top - t.height - 10 : r.bottom + 10)}px`;
    tip.style.setProperty("--ax", `${Math.round(cx - left)}px`);
    tip.setAttribute("data-side", above ? "top" : "bottom");
  };
  on(report, "pointerover", (e: PointerEvent) => { const el = (e.target as Element).closest?.<HTMLElement>(TIPPED); if (el && el !== tipFor) showTip(el); });
  on(report, "pointerout", (e: PointerEvent) => { const el = (e.target as Element).closest?.(TIPPED); if (el && !(e.relatedTarget instanceof Node && el.contains(e.relatedTarget))) hideTip(); });
  on(report, "focusin", (e: FocusEvent) => { const el = (e.target as Element).closest?.<HTMLElement>(TIPPED); if (el) showTip(el); else hideTip(); });
  on(report, "focusout", (e: FocusEvent) => { if (!(e.relatedTarget instanceof Element && e.relatedTarget.closest(TIPPED))) hideTip(); });
  on(win, "scroll", hideTip, { passive: true });

  // Roving focus: each tapestry, cost panel and invalid group is one tab stop.
  // Arrow keys move between its marks, Home and End go to the ends, and Enter
  // or Space opens the run (they are buttons). The last mark focused keeps the stop.
  const groupOf = (el: Element) => el.closest<HTMLElement>("[data-av-roving], .av-strip-panel, .av-inv-group, .av-block");
  const groups = new Map<HTMLElement, HTMLElement[]>();
  for (const m of all(MARKS)) {
    if (dialog?.contains(m)) continue;
    const g = groupOf(m);
    if (!g) continue;
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g)!.push(m);
  }
  for (const items of groups.values()) items.forEach((m, i) => { m.tabIndex = i === 0 ? 0 : -1; });
  const shown = (el: Element) => el.getClientRects().length > 0;
  const centre = (el: Element) => { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, h: r.height, r }; };
  const nearestX = (pool: HTMLElement[], x: number) => pool.reduce<HTMLElement | null>((best, el) => !best || Math.abs(centre(el).x - x) < Math.abs(centre(best).x - x) ? el : best, null);
  const vertical = (m: HTMLElement, items: HTMLElement[], dir: 1 | -1): HTMLElement | null => {
    const c = centre(m), unitSel = ".av-tap-cell, [data-av-cell]", rowSel = ".av-tap-row, .av-strip-row, [data-av-row]";
    const unit = m.closest(unitSel), row = m.closest(rowSel);
    const below = (el: HTMLElement, gap: number) => (centre(el).y - c.y) * dir > gap;
    const closest = (pool: HTMLElement[]) => {
      let best: HTMLElement | null = null, bestDy = Infinity, bestDx = Infinity;
      for (const el of pool) {
        const p = centre(el), dy = (p.y - c.y) * dir, dx = Math.abs(p.x - c.x);
        if (dy < bestDy - 3 || (Math.abs(dy - bestDy) <= 3 && dx < bestDx)) { best = el; bestDy = dy; bestDx = dx; }
      }
      return best;
    };
    // Wrapped marks inside one cell, then cells stacked inside one row (narrow layouts).
    if (unit) { const hit = closest(items.filter(el => el !== m && el.closest(unitSel) === unit && below(el, c.h * 0.75))); if (hit) return hit; }
    if (row && unit) {
      const ur = unit.getBoundingClientRect();
      const hit = closest(items.filter(el => { const u = el.closest(unitSel); if (!u || u === unit || el.closest(rowSel) !== row) return false; const r = u.getBoundingClientRect(); return dir > 0 ? r.top >= ur.bottom - 1 : r.bottom <= ur.top + 1; }));
      if (hit) return hit;
    }
    if (!row) return closest(items.filter(el => el !== m && below(el, c.h * 0.75)));
    const rows: Element[] = [];
    for (const el of items) { const r = el.closest(rowSel); if (r && !rows.includes(r)) rows.push(r); }
    const target = rows[rows.indexOf(row) + dir];
    return target ? nearestX(items.filter(el => el.closest(rowSel) === target), c.x) : null;
  };
  const moveMark = (m: HTMLElement, key: string): boolean => {
    const items = (groups.get(groupOf(m)!) || []).filter(shown), at = items.indexOf(m);
    if (at < 0) return false;
    const next = key === "ArrowRight" ? items[at + 1] : key === "ArrowLeft" ? items[at - 1] : key === "Home" ? items[0] : key === "End" ? items[items.length - 1]
      : key === "ArrowDown" ? vertical(m, items, 1) : key === "ArrowUp" ? vertical(m, items, -1) : undefined;
    if (next === undefined) return false;
    if (next) { next.focus(); next.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }
    return true;
  };
  on(report, "focusin", (e: FocusEvent) => {
    const m = (e.target as Element).closest?.<HTMLElement>(MARKS);
    const items = m && groups.get(groupOf(m)!);
    if (m && items) for (const x of items) x.tabIndex = x === m ? 0 : -1;
  });

  // Run drawer --------------------------------------------------------------
  let currentRun = -1, hashBefore: string | null = null;
  const sequence = (): number[] => {
    const rows = all("table.av-ledger tbody tr[data-run]").filter(r => !r.hidden).map(r => Number(r.dataset.run)).filter(n => Number.isInteger(n));
    return rows.length ? rows : (data?.runs || []).map((_, i) => i);
  };
  const runSummary = (i: number) => {
    const r = data!.runs[i], o = outcomeOf(r);
    let cause = "";
    try { cause = failureCause(r, scenarioOf(data!, r)).text; } catch { cause = ""; }
    return `Run ${i + 1} of ${data!.runs.length}: ${ctx!.caseLabels[r.scenario] || r.scenario}, ${ctx!.arms.label(r.arm)}, repeat ${r.repeat ?? "?"}, ${outcomeLabel[o]}.${cause ? " " + cause.replace(/`/g, "") : ""}`;
  };
  const openRun = (i: number, opener?: HTMLElement | null, focus = ".av-drawer-close"): boolean => {
    if (!dialog || !data || !ctx || !data.runs[i]) return false;
    const fresh = !dialog.open;
    currentRun = i;
    hideTip();
    dialog.querySelector<HTMLElement>("[data-av-drawer-body]")!.innerHTML = drawerHtml(data, i, ctx, sequence());
    if (fresh) {
      (dialog as any).__opener = opener;
      if (hashBefore === null) hashBefore = currentHash();
      typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", "");
    }
    (dialog.querySelector<HTMLElement>(focus) || dialog.querySelector<HTMLElement>(".av-drawer-close"))?.focus();
    setHash(`#run-${i + 1}`);
    if (!fresh) announce(runSummary(i), drawerLive);
    return true;
  };
  const step = (dir: 1 | -1, focus?: string) => {
    const seq = sequence(), at = seq.indexOf(currentRun);
    openRun(seq[((at < 0 ? 0 : at) + dir + seq.length) % seq.length], undefined, focus);
  };
  // Closing restores the address the reader had before the drawer opened. The
  // close event covers Escape; the drawer's own button restores it at once.
  const restoreHash = () => { if (hashBefore !== null) { setHash(hashBefore); hashBefore = null; } };
  const closeDrawer = () => { restoreHash(); dialog?.close(); };
  if (dialog && data && ctx) {
    on(dialog, "close", () => {
      const opener = (dialog as any).__opener as HTMLElement | undefined;
      restoreHash(); currentRun = -1;
      if (opener?.isConnected !== false) opener?.focus?.();
    });
  }

  // Ledger ----------------------------------------------------------------
  interface Ledger { sectionId: string; restore(params: URLSearchParams): void }
  const ledgers: Ledger[] = [];
  // The run ledger, and any other record table (table[data-av-table], such as the
  // observations block): the same filters, sorting and phone cards, without the
  // run drawer, the row keyboard model or the trial export.
  for (const table of all<HTMLTableElement>("table.av-ledger, table[data-av-table]")) {
    const block = table.closest<HTMLElement>(".av-block"), tbody = table.tBodies[0];
    if (!block || !tbody) continue;
    const n = ++ledgerSeq;
    const generic = table.hasAttribute("data-av-table"), rowAttr = generic ? "data-av-row" : "data-run", noun = table.getAttribute("data-av-noun") || "runs";
    const wrapOf = () => block.querySelector(".av-ledger-wrap") || table.closest(".av-scroll-x") || table;
    const rows = Array.from(tbody.rows).filter(r => r.hasAttribute(rowAttr));
    const heads = Array.from(table.tHead?.rows[0]?.cells || []);
    // Name each column, so narrow screens can lay a row out as a card, and keep
    // table semantics explicit for when CSS changes the display of its parts.
    const keys = heads.map(th => th.getAttribute("data-col") || ((th.textContent || "").trim() === "#" ? "n" : (th.textContent || "").trim().toLowerCase().split(/\s+/)[0].replace(/[^a-z0-9-]/g, "")));
    table.setAttribute("role", "table");
    table.tHead?.setAttribute("role", "rowgroup"); tbody.setAttribute("role", "rowgroup");
    heads.forEach((th, i) => { th.setAttribute("data-col", keys[i]); th.setAttribute("role", "columnheader"); });
    table.tHead?.rows[0]?.setAttribute("role", "row");
    for (const r of rows) { r.setAttribute("role", "row"); Array.from(r.cells).forEach((c, i) => { if (keys[i] && !c.hasAttribute("data-col")) c.setAttribute("data-col", keys[i]); c.setAttribute("role", "cell"); }); }

    // One tab stop for the rows; ↑ ↓ Home End move, Enter or Space opens.
    let current: HTMLTableRowElement | undefined;
    const setCurrent = (r: HTMLTableRowElement | undefined) => { if (generic) return; if (current && current !== r) current.tabIndex = -1; current = r; if (r) r.tabIndex = 0; };
    if (!generic) {
      const hint = make("span", { class: "av-sr", id: `av-ledger-hint-${n}` }, "Press Enter to open this run's record. Up and down arrows move between runs.");
      if (hint) block.appendChild(hint);
      rows.forEach(r => { r.tabIndex = -1; if (hint) r.setAttribute("aria-describedby", hint.id); });
      setCurrent(rows[0]);
      on(tbody, "focusin", (e: FocusEvent) => { const r = (e.target as Element).closest?.<HTMLTableRowElement>("tr[data-run]"); if (r) setCurrent(r); });
      on(tbody, "keydown", (e: KeyboardEvent) => {
        const r = (e.target as Element).closest?.<HTMLTableRowElement>("tr[data-run]");
        if (!r || !["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
        const visible = Array.from(tbody.rows).filter(x => x.hasAttribute("data-run") && !x.hidden && !(narrow() && x.hasAttribute("data-av-beyond"))), at = visible.indexOf(r);
        const next = e.key === "ArrowDown" ? visible[at + 1] : e.key === "ArrowUp" ? visible[at - 1] : e.key === "Home" ? visible[0] : visible[visible.length - 1];
        e.preventDefault();
        if (next) { next.focus(); next.scrollIntoView?.({ block: "nearest" }); }
      });
    }

    // Narrow screens list runs as cards: the first PHONE_ROWS that match show until
    // the reader asks for the rest, so the filters and the end of the page stay near.
    // Wider screens ignore the mark; the table scrolls in its own frame there.
    const PHONE_ROWS = 20;
    let showAll = false, moreButton: HTMLElement | null = null;
    const clipRows = () => {
      let k = 0;
      for (const r of rows) { if (!r.hidden) k++; if (!showAll && !r.hidden && k > PHONE_ROWS) r.setAttribute("data-av-beyond", ""); else r.removeAttribute("data-av-beyond"); }
      if (moreButton) { moreButton.hidden = showAll || k <= PHONE_ROWS; moreButton.textContent = `Show all ${k} ${noun}`; }
    };

    // Sorting by column header, or by the select narrow screens show instead.
    const sortable = all<HTMLTableCellElement>("th[data-sortable]", table);
    let sortSelect: HTMLSelectElement | null = null;
    const sortBy = (th: HTMLTableCellElement, dir: "ascending" | "descending") => {
      sortable.forEach(x => x.setAttribute("aria-sort", "none"));
      th.setAttribute("aria-sort", dir);
      const index = heads.indexOf(th), numeric = th.dataset.sortable === "num";
      const key = (r: HTMLTableRowElement) => { const c = r.cells[index]; const raw = c?.dataset.sort ?? c?.textContent ?? ""; return numeric ? (Number.isFinite(parseFloat(raw)) ? parseFloat(raw) : -Infinity) : raw.trim().toLowerCase(); };
      rows.sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) * (dir === "ascending" ? 1 : -1) || Number(a.dataset.run ?? a.dataset.avRow) - Number(b.dataset.run ?? b.dataset.avRow); });
      rows.forEach(r => tbody.appendChild(r));
      if (emptyRow) tbody.appendChild(emptyRow);
      clipRows();
      if (sortSelect) sortSelect.value = Array.from(sortSelect.options).some(o => o.value === `${index}:${dir}`) ? `${index}:${dir}` : "";
    };
    sortable.forEach(th => {
      th.tabIndex = 0; th.setAttribute("aria-sort", "none");
      const sort = () => sortBy(th, th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending");
      on(th, "click", sort); on(th, "keydown", (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    });

    // An empty view says so and offers the way back.
    const emptyRow = make("tr", { class: "av-ledger-empty", "data-av-empty": "", hidden: "" }) as HTMLTableRowElement | null;
    let clearAll = () => { /* set once the tools exist */ };
    if (emptyRow) {
      const cell = make("td", { colspan: String(Math.max(1, heads.length)) });
      const text = make("span", {}, `No ${noun} match these filters. `);
      const clear = make("button", { type: "button", class: "av-btn av-btn--small" }, "Clear filters");
      if (cell && text && clear) { cell.append(text, clear); emptyRow.appendChild(cell); on(clear, "click", () => clearAll()); }
      tbody.appendChild(emptyRow);
    }

    const tools = block.querySelector<HTMLElement>("[data-av-ledger-tools]");
    const count = block.querySelector<HTMLOutputElement>(".av-ledger-count");
    const sectionId = block.closest<HTMLElement>(".av-section[id]")?.id || "";
    let outcome = "", exportLabel: HTMLElement | null = null;
    const exportShown: HTMLButtonElement[] = [];
    // Every select[data-filter] narrows by the row attribute it names (arm, case, metric, …).
    const selects = tools ? all<HTMLSelectElement>("select[data-filter]", tools) : [];
    const search = tools?.querySelector<HTMLInputElement>('[data-filter="text"]') || null;
    const outcomeButtons = tools ? all<HTMLButtonElement>("[data-outcome]", tools) : [];
    let clearButton: HTMLElement | null = null;
    // The page region announces counts; the output keeps showing them.
    count?.removeAttribute("aria-live");
    let announceQueued = 0;
    const apply = (fromUser: boolean) => {
      const picks = selects.map(sel => [sel.dataset.filter || "", sel.value] as const).filter(([k, v]) => k && v);
      const q = (search?.value || "").trim().toLowerCase();
      let shownCount = 0;
      for (const r of rows) {
        const ok = (!outcome || r.dataset.outcome === outcome) && picks.every(([k, v]) => r.dataset[k] === v) && (!q || (r.textContent || "").toLowerCase().includes(q));
        r.hidden = !ok; if (ok) shownCount++;
      }
      const active = !!(outcome || picks.length || q);
      const words = `${shownCount} of ${rows.length} ${noun}`;
      if (count) count.textContent = words;
      if (emptyRow) emptyRow.hidden = shownCount > 0;
      if (clearButton) clearButton.hidden = !active;
      if (exportLabel) exportLabel.textContent = shownCount === rows.length ? `all ${rows.length} runs` : `the ${shownCount} run${shownCount === 1 ? "" : "s"} shown`;
      for (const b of exportShown) b.disabled = shownCount === 0;
      clipRows();
      if (!generic && (!current || current.hidden)) setCurrent(rows.find(r => !r.hidden) || current);
      if (!fromUser) return;
      if (sectionId && !dialog?.open) {
        const params = new URLSearchParams();
        if (outcome) params.set("outcome", outcome);
        for (const [k, v] of picks) params.set(k, v);
        if (q) params.set("q", search!.value.trim());
        const qs = params.toString();
        if (qs || currentHash().startsWith(`#${sectionId}?`)) setHash(`#${sectionId}${qs ? "?" + qs : ""}`);
      }
      const ticket = ++announceQueued;
      later(() => { if (ticket === announceQueued) announce(active ? `${words} shown.` : `All ${rows.length} ${noun} shown.`, pageLive); }, 450);
    };
    const setOutcome = (value: string) => {
      const button = outcomeButtons.find(b => (b.dataset.outcome || "") === value && !b.disabled);
      outcome = button ? value : "";
      outcomeButtons.forEach(b => b.setAttribute("aria-pressed", String((b.dataset.outcome || "") === outcome)));
    };
    clearAll = () => {
      setOutcome("");
      for (const sel of selects) sel.value = ""; if (search) search.value = "";
      apply(true);
      (search || outcomeButtons[0])?.focus();
    };
    if (tools) {
      tools.hidden = false;
      for (const b of outcomeButtons) {
        if (b.dataset.outcome && !rows.some(r => r.dataset.outcome === b.dataset.outcome)) { b.disabled = true; b.setAttribute("aria-disabled", "true"); }
        on(b, "click", () => { setOutcome(b.dataset.outcome || ""); apply(true); });
      }
      for (const el of [...selects, search]) on(el, "input", () => apply(true));
      // Narrow screens hide the header row, so sorting moves into a select.
      if (sortable.length) {
        const field = make("label", { class: "av-field av-sort-field" });
        const caption = make("span", {}, "Sort by");
        sortSelect = make("select", { "data-av-sort": "" }) as HTMLSelectElement | null;
        if (field && caption && sortSelect) {
          const option = (value: string, text: string) => { const o = make("option", { value }, text); if (o) sortSelect!.appendChild(o); };
          option("", "As listed");
          for (const th of sortable) {
            const i = heads.indexOf(th), label = keys[i] === "n" ? (generic ? "Row number" : "Run number") : (th.textContent || "").trim();
            if (th.dataset.sortable === "num") { option(`${i}:descending`, `${label}, highest first`); option(`${i}:ascending`, `${label}, lowest first`); }
            else option(`${i}:ascending`, `${label}, A to Z`);
          }
          field.append(caption, sortSelect);
          if (count && count.parentElement === tools) tools.insertBefore(field, count); else tools.appendChild(field);
          const sel = sortSelect;
          on(sel, "input", () => {
            const [index, dir] = sel.value.split(":");
            const th = heads[Number(index)];
            if (th && (dir === "ascending" || dir === "descending")) sortBy(th, dir);
            else { const nTh = heads[keys.indexOf("n")]; if (nTh?.hasAttribute("data-sortable")) { sortBy(nTh, "ascending"); nTh.setAttribute("aria-sort", "none"); } sel.value = ""; }
          });
        }
      }
      clearButton = make("button", { type: "button", class: "av-btn av-btn--small av-ledger-clear", "data-av-clear": "", hidden: "" }, "Clear filters");
      if (clearButton) { tools.appendChild(clearButton); on(clearButton, "click", () => clearAll()); }
    }

    // Export: the runs in view, in their order, as CSV; the whole trial as JSON.
    if (data && ctx && !generic) {
      const bar2 = make("div", { class: "av-ledger-export", role: "group", "aria-label": "Export runs" });
      const lead = make("span", { class: "av-ledger-export-lead" }, "Export ");
      exportLabel = make("span", { class: "av-ledger-export-what" }, `all ${rows.length} runs`);
      const csvButton = make("button", { type: "button", class: "av-btn av-btn--small", "data-av-export": "csv" }, "Download CSV");
      const copyButton = make("button", { type: "button", class: "av-btn av-btn--small", "data-av-export": "copy" });
      const jsonButton = make("button", { type: "button", class: "av-btn av-btn--small av-ledger-export-all", "data-av-export": "json" }, "Download all trial data (JSON)");
      const status = make("p", { class: "av-export-status", role: "status" });
      if (bar2 && lead && exportLabel && csvButton && copyButton && jsonButton && status) {
        exportShown.push(csvButton as HTMLButtonElement, copyButton as HTMLButtonElement);
        const copyWord = make("span", { "data-av-word": "" }, "Copy CSV");
        if (copyWord) copyButton.appendChild(copyWord);
        lead.append(exportLabel, ":");
        bar2.append(lead, csvButton, copyButton, jsonButton);
        wrapOf().after(bar2); bar2.after(status);
        const stem = fileStem(data.name);
        const shownRuns = () => rows.filter(r => !r.hidden).map(r => Number(r.dataset.run));
        const csv = () => runsCsv(data, shownRuns(), { arm: id => ctx.arms.label(id), case: id => ctx.caseLabels[id] || id });
        const blocked = "This viewer may block downloads; Copy CSV puts the same rows on the clipboard, or open the report file directly in a browser.";
        on(csvButton, "click", () => {
          const runsShown = shownRuns().length, name = `${stem}-runs.csv`;
          status.textContent = download(name, "\ufeff" + csv(), "text/csv;charset=utf-8") ? `Saving ${name}: ${runsShown} run${runsShown === 1 ? "" : "s"}, one row each. Nothing saved? ${blocked}` : `The download was refused. ${blocked}`;
          announce(status.textContent, pageLive);
        });
        on(copyButton, "click", async () => {
          const runsShown = shownRuns().length, ok = await copyText(csv(), copyButton);
          flash(copyButton, ok ? "Copied" : "Copy blocked");
          status.textContent = ok ? `Copied ${runsShown} run${runsShown === 1 ? "" : "s"} as CSV; paste into a spreadsheet.` : "This viewer blocks the clipboard. Download CSV saves the same rows as a file.";
          announce(status.textContent, pageLive);
        });
        on(jsonButton, "click", () => {
          const name = `${stem}-trial.json`;
          status.textContent = download(name, JSON.stringify(data, null, 2) + "\n", "application/json") ? `Saving ${name}: the complete trial data this report draws from (${data.runs.length} runs). Nothing saved? This viewer may block downloads; the same JSON is embedded in the report file's source.` : "The download was refused. The same JSON is embedded in the report file's source.";
          announce(status.textContent, pageLive);
        });
      }
    }

    moreButton = make("button", { type: "button", class: "av-btn av-btn--small av-ledger-more", "data-av-more": "", hidden: "" });
    if (moreButton) {
      wrapOf().after(moreButton);
      on(moreButton, "click", () => {
        showAll = true; clipRows();
        const next = rows.filter(r => !r.hidden)[PHONE_ROWS];
        if (next) { setCurrent(next); next.focus(); }
      });
    }
    clipRows();

    ledgers.push({
      sectionId,
      restore(params: URLSearchParams) {
        setOutcome(params.get("outcome") || "");
        const pick = (sel: HTMLSelectElement | null, value: string | null) => { if (sel) sel.value = value && Array.from(sel.options).some(o => o.value === value) ? value : ""; };
        for (const sel of selects) pick(sel, params.get(sel.dataset.filter || ""));
        if (search) search.value = params.get("q") || "";
        apply(false);
      },
    });
    apply(false);
  }

  // Footer: the embedded data, for any report that carries a trial.
  const footer = report.querySelector<HTMLElement>(".av-footer");
  if (footer && data && !footer.querySelector("[data-av-export]")) {
    const p = make("p", { class: "av-footer-export" });
    const button = make("button", { type: "button", class: "av-btn av-btn--small", "data-av-export": "json-footer" }, "Download the trial data (JSON)");
    const status = make("span", { class: "av-export-status", role: "status" });
    if (p && button && status) {
      p.append(button, status); footer.appendChild(p);
      on(button, "click", () => {
        const name = `${fileStem(data.name)}-trial.json`;
        status.textContent = download(name, JSON.stringify(data, null, 2) + "\n", "application/json") ? ` Saving ${name}. Nothing saved? This viewer may block downloads; the JSON is also embedded in this file's source.` : " The download was refused; the JSON is embedded in this file's source.";
      });
    }
  }

  // Clicks and keys ----------------------------------------------------------
  // One delegated click handler for the report and its drawer.
  if (dialog && data && ctx) {
    on(report, "click", async (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (dialog.contains(t)) {
        const nav = t.closest<HTMLElement>("[data-av-nav]");
        const copy = t.closest<HTMLElement>("[data-av-copy]"), copyLink = t.closest<HTMLElement>("[data-av-copy-link]");
        if (nav) step(nav.dataset.avNav === "next" ? 1 : -1, `[data-av-nav="${nav.dataset.avNav === "next" ? "next" : "prev"}"]`);
        else if (t.closest(".av-drawer-close") || t === dialog) closeDrawer();
        else if (copyLink) {
          const ok = await copyText(linkTo(`#run-${currentRun + 1}`), copyLink);
          flash(copyLink, ok ? "Copied" : "In address bar");
          announce(ok ? "Link to this run copied." : "Copying is blocked here; the address bar holds the link to this run.", drawerLive);
        } else if (copy) {
          const ok = await copyText(copy.dataset.avCopy || "", copy);
          flash(copy, ok ? "Copied" : "Selected");
          if (!ok) selectText(copy.previousElementSibling);
          announce(ok ? "Path copied." : "Copying is blocked here; the path is selected for copying by hand.", drawerLive);
        }
        return;
      }
      const run = t.closest<HTMLElement>("[data-run]");
      if (run && report.contains(run)) openRun(Number(run.dataset.run), run);
    });
  }
  on(report, "keydown", (e: KeyboardEvent) => {
    const t = e.target as HTMLElement;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (dialog?.open && dialog.contains(t)) {
      if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && !t.closest(FIELDS) && data) {
        e.preventDefault();
        const nav = t.closest<HTMLElement>("[data-av-nav]"), close = t.closest(".av-drawer-close"), link = t.closest("[data-av-copy-link]");
        step(e.key === "ArrowRight" ? 1 : -1, nav ? `[data-av-nav="${nav.dataset.avNav === "next" ? "next" : "prev"}"]` : link ? "[data-av-copy-link]" : close ? ".av-drawer-close" : ".av-drawer-close");
      }
      return;
    }
    if ((e.key === "Enter" || e.key === " ") && t.matches?.("tr[data-run]")) { e.preventDefault(); openRun(Number(t.dataset.run), t); return; }
    if (t.matches?.(MARKS) && moveMark(t, e.key)) { e.preventDefault(); return; }
    if (e.key === "Escape") hideTip();
  });
  // "/" jumps to the ledger search from anywhere outside a field.
  on(doc, "keydown", (e: KeyboardEvent) => {
    if (e.key !== "/" || e.altKey || e.ctrlKey || e.metaKey || dialog?.open) return;
    const t = e.target as Element | null;
    if (t?.closest?.(FIELDS)) return;
    const field = report.querySelector<HTMLInputElement>('[data-av-ledger-tools] [data-filter="text"]');
    if (!field || !shown(field)) return;
    e.preventDefault(); field.focus(); field.scrollIntoView?.({ block: "center" });
  });

  // Deep links ---------------------------------------------------------------
  const parseHash = (raw: string) => {
    let h = raw.replace(/^#/, "");
    try { h = decodeURIComponent(h); } catch { /* keep it raw */ }
    const q = h.indexOf("?");
    return { id: q >= 0 ? h.slice(0, q) : h, params: q >= 0 ? h.slice(q + 1) : "" };
  };
  const runFromId = (id: string): number => {
    const m = /^run[-=](.+)$/.exec(id);
    if (!m || !data) return -1;
    if (/^\d+$/.test(m[1])) { const k = Number(m[1]); return k >= 1 && k <= data.runs.length ? k - 1 : -1; }
    return data.runs.findIndex(r => r.job === m[1]);
  };
  const jumpTo = (el: HTMLElement) => {
    const html = doc.documentElement, before = html.style.scrollBehavior;
    html.style.scrollBehavior = "auto";
    el.scrollIntoView?.({ block: "start" });
    later(() => { html.style.scrollBehavior = before; }, 1200);
  };
  const markTarget = (section: HTMLElement, initial: boolean) => {
    const heading = section.querySelector<HTMLElement>(".av-section-title");
    const focus = () => { if (!heading) return; if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1"); try { heading.focus({ preventScroll: true }); } catch { heading.focus(); } };
    focus();
    // The browser's own fragment handling at load can reset focus; take it back
    // once, if nothing else has it by then.
    if (initial) {
      const again = () => { if (!doc.activeElement || doc.activeElement === doc.body) focus(); };
      if (doc.readyState === "complete") later(again, 0); else on(win, "load", () => later(again, 0), { once: true });
    }
    section.setAttribute("data-av-target", "");
    later(() => section.removeAttribute("data-av-target"), 1700);
  };
  const route = (initial: boolean) => {
    const { id, params } = parseHash(currentHash());
    if (!id) return;
    const el = typeof doc.getElementById === "function" ? doc.getElementById(id) : null;
    if (el && report.contains(el)) {
      if (params) for (const l of ledgers) if (l.sectionId === id) l.restore(new URLSearchParams(params));
      if (initial) jumpTo(el);
      if (el.matches(".av-section")) markTarget(el, initial);
      return;
    }
    const i = runFromId(id);
    if (i >= 0) {
      if (initial || !dialog?.open) hashBefore = "";
      openRun(i, null);
    }
  };
  on(win, "hashchange", () => route(false));
  route(true);

  // Printing: paper gets the light theme and every collapsed case opened.
  let printState: { theme: string | null; opened: HTMLDetailsElement[] } | null = null;
  on(win, "beforeprint", () => {
    const html = doc.documentElement;
    printState = { theme: html.getAttribute("data-theme"), opened: all<HTMLDetailsElement>("details:not([open])").filter(d => !dialog?.contains(d)) };
    printState.opened.forEach(d => { d.open = true; });
    html.setAttribute("data-theme", "light");
  });
  on(win, "afterprint", () => {
    if (!printState) return;
    const html = doc.documentElement;
    printState.opened.forEach(d => { d.open = false; });
    if (printState.theme === null) html.removeAttribute("data-theme"); else html.setAttribute("data-theme", printState.theme);
    printState = null;
  });

  // Diagrams --------------------------------------------------------------
  if (report.querySelector("[data-av-mermaid]")) { diagrams = attachMermaid(report, () => undefined); void diagrams.refresh(); }
  // Diagrams read theme colors when drawn; redraw when the system theme flips.
  const media = win.matchMedia?.("(prefers-color-scheme: dark)");
  if (media && diagrams) on(media, "change", () => { void diagrams?.refresh(); });

  report.setAttribute("data-av-ready", "");
  const Ev = win.Event; doc.dispatchEvent(new Ev("av-report-ready"));
  return {
    diagrams,
    cleanup() {
      offs.splice(0).forEach(f => f());
      sizes?.disconnect(); children?.disconnect();
      if (typeof win.clearTimeout === "function") timers.forEach(id => win.clearTimeout(id));
      timers.clear();
      diagrams?.cleanup();
      added.splice(0).forEach(el => el.remove());
      report.removeAttribute("data-av-ready");
    },
  };
}

// ------------------------------------------------------------------ drawer

function drawerHtml(data: TrialReport, i: number, ctx: RenderContext, seq: number[]): string {
  const r = data.runs[i], o = outcomeOf(r), at = seq.indexOf(i), total = data.runs.length;
  const scenario = scenarioOf(data, r);
  const requiredList = Array.isArray(scenario?.required) ? scenario!.required.filter((c): c is string => typeof c === "string") : [];
  const required = new Set(requiredList);
  const caseName = ctx.caseLabels[r.scenario] || r.scenario;
  let cause = { kind: "none", text: "", failedChecks: [] as string[] };
  try { cause = failureCause(r, scenario); } catch { /* the checks below still show everything recorded */ }
  const view = at >= 0 && (seq.length !== total || at !== i) ? ` · ${at + 1} of ${seq.length} in the ledger's current view` : "";

  // Why: the first thing a reader of a failed or invalid run needs.
  let why = "";
  if (o !== "pass") {
    const text = cause.text || (o === "invalid" ? "No valid result, and no reason was recorded." : "Failed; this report could not name a cause. Everything the run recorded is below.");
    const remedy = o === "invalid" ? invalidReason(r.invalid_reason || r.status || "").remedy : "";
    why = `<div class="av-drawer-why av-drawer-why--${o}"><p><span class="av-drawer-why-label">${o === "invalid" ? "Why there is no result" : "Why it failed"}</span>${inline(text)}</p>${remedy ? `<p class="av-drawer-remedy"><span class="av-drawer-why-label">What gives it a result</span>${inline(remedy)}</p>` : ""}</div>`;
  }

  const positive = (v: unknown) => isNum(v) && v > 0;
  const facts: Array<[string, string]> = [
    ["Status", r.status ? `<code>${esc(r.status)}</code>` : '<span class="av-missing">not recorded</span>'],
    ...(o === "invalid" ? [["Invalid because", `<code>${esc(r.invalid_reason || r.status || "unknown")}</code>`] as [string, string]] : []),
    ["Executor time", isNum(r.seconds) ? esc(fmtSeconds(r.seconds)) : '<span class="av-missing">not recorded</span>'],
    ...(positive(r.setup_seconds) ? [["Setup", esc(fmtSeconds(r.setup_seconds))] as [string, string]] : []),
    ...(positive(r.checks_seconds) ? [["Checks", esc(fmtSeconds(r.checks_seconds))] as [string, string]] : []),
    ...(r.judge || positive(r.judge_seconds) ? [["Judge", isNum(r.judge_seconds) ? esc(fmtSeconds(r.judge_seconds)) : '<span class="av-missing">not recorded</span>'] as [string, string]] : []),
    ...(isNum(r.commands) ? [["Commands", esc(fmtNum(r.commands))] as [string, string]] : []),
    ...(r.confined === false ? [["Sandbox", "<strong>unconfined</strong>"] as [string, string]] : []),
    ...(r.artifact_missing ? [["Artifact", "<strong>not produced</strong>"] as [string, string]] : []),
  ];

  // Checks: required ones first (those that did not hold at the top), then the
  // other true/false checks, then recorded values folded away.
  const checks = r.checks && typeof r.checks === "object" ? r.checks : {};
  const has = (k: string) => Object.prototype.hasOwnProperty.call(checks, k);
  const value = (v: unknown) => typeof v === "boolean"
    ? `${outcomeMark(v ? "pass" : "fail")}<span>${v ? "true" : "false"}</span>`
    : v === undefined || v === null ? '<span class="av-missing">not recorded</span>' : `<code>${esc(typeof v === "string" ? v : JSON.stringify(v))}</code>`;
  const rank = (k: string) => { const v = checks[k]; return v === false ? 0 : v === true ? 2 : 1; };
  // An invalid run has no result, so its checks decide nothing: listed, not flagged.
  const decides = o !== "invalid";
  const reqRows = requiredList.slice().sort((a, b) => decides ? rank(a) - rank(b) : 0).map(k => {
    const held = checks[k] === true || !decides;
    return `<tr class="av-req${held ? "" : " av-req--unmet"}"><th scope="row"><code>${esc(k).replace(/_/g, "_<wbr>")}</code> <span class="av-chip av-chip--req">required</span></th><td>${has(k) ? value(checks[k]) : value(undefined)}</td></tr>`;
  }).join("");
  const others = Object.entries(checks).filter(([k]) => !required.has(k));
  const bools = others.filter(([, v]) => typeof v === "boolean"), values = others.filter(([, v]) => typeof v !== "boolean");
  const unmet = requiredList.filter(k => checks[k] !== true).length;
  const table = (body: string) => `<table class="av-table av-table--compact av-drawer-checks"><tbody>${body}</tbody></table>`;
  const plainRows = (items: Array<[string, unknown]>) => items.map(([k, v]) => `<tr><th scope="row"><code>${esc(k).replace(/_/g, "_<wbr>")}</code></th><td>${value(v)}</td></tr>`).join("");
  const checkSecs = [
    requiredList.length ? `<section class="av-drawer-sec"><h3>Required checks <span class="av-muted">· ${!decides ? "as recorded; a run with no result is not scored" : unmet ? `${unmet} of ${requiredList.length} did not hold` : requiredList.length === 1 ? "it held" : `all ${requiredList.length} held`}</span></h3>${table(reqRows)}</section>` : "",
    bools.length ? `<section class="av-drawer-sec"><h3>${requiredList.length ? "Other checks" : "Checks"} <span class="av-muted">· recorded${requiredList.length ? ", not required" : ""}</span></h3>${table(plainRows(bools))}</section>` : "",
    values.length ? `<details class="av-drawer-sec av-drawer-values"${values.length <= 4 ? " open" : ""}><summary>${values.length} recorded value${values.length === 1 ? "" : "s"} <span class="av-muted">· text and numbers the checks wrote</span></summary>${table(plainRows(values))}</details>` : "",
  ].join("");

  const usage = Object.entries(r.usage && typeof r.usage === "object" ? r.usage : {}).filter(([, v]) => isNum(v) && v !== 0);
  const path = recordPath(data, r);
  const q = judgeQuestion(scenario);
  return `<header class="av-drawer-head"><div class="av-drawer-id"><p class="av-eyebrow">Run ${i + 1} of ${total}${r.job ? ` · <code>${esc(r.job)}</code>` : ""}${esc(view)}</p><h2 id="av-drawer-title" class="av-drawer-title">${esc(caseName)}</h2><p class="av-drawer-sub">${ctx.arms.tag(r.arm)}<span>repeat ${esc(r.repeat ?? "?")}</span>${outcomeBadge(o)}</p></div><div class="av-drawer-actions"><button type="button" class="av-btn av-btn--small" data-av-copy-link aria-label="Copy a link to this run"><span data-av-word>Copy link</span></button><button type="button" class="av-drawer-close" aria-label="Close run record">✕</button></div></header>
<div class="av-drawer-scroll">
${why}
<dl class="av-facts av-facts--tight">${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join("")}</dl>
${r.judge ? `<section class="av-drawer-sec"><h3>Judge <span class="av-judge av-judge--${esc(r.judge.verdict || "none")}">${esc(r.judge.verdict || "no verdict")}</span></h3>${r.judge.reason ? `<p class="av-drawer-text">${inline(String(r.judge.reason))}</p>` : '<p class="av-muted">The judge gave no reason.</p>'}${q ? `<details class="av-drawer-q"><summary>Question the judge answered</summary><p class="av-drawer-text">${esc(q)}</p></details>` : ""}</section>` : ""}
${checkSecs}
${r.final_message_excerpt ? `<section class="av-drawer-sec"><h3>Final output${r.final_message_excerpt.length >= 2000 ? ' <span class="av-muted">· first 2,000 characters; the full text is in the native record</span>' : ""}</h3><pre class="av-pre av-pre--tall">${esc(r.final_message_excerpt)}</pre></section>` : ""}
${usage.length ? `<section class="av-drawer-sec"><h3>Usage <span class="av-muted">· as the executor reported it</span></h3><dl class="av-facts av-facts--tight av-drawer-usage">${usage.map(([k, v]) => `<div><dt><code>${esc(k)}</code></dt><dd>${esc(fmtNum(v))}</dd></div>`).join("")}</dl></section>` : ""}
${path ? `<section class="av-drawer-sec"><h3>Native record</h3><p class="av-drawer-path"><code>${esc(displayPath(path))}</code><button type="button" class="av-btn av-btn--small" data-av-copy="${esc(path)}"><span data-av-word>Copy path</span></button></p><p class="av-muted">The full transcript, events, checks and judge prompt live in this directory.</p></section>` : ""}
</div>
<footer class="av-drawer-foot"><button type="button" class="av-btn" data-av-nav="prev" aria-label="Previous run">← Previous</button><span class="av-muted">${esc(outcomeLabel[o])}<span class="av-drawer-keys"> · ← → to move</span></span><button type="button" class="av-btn" data-av-nav="next" aria-label="Next run">Next →</button></footer>`;
}

/** Render a specification into a target and enhance it. */
export function mount(target: HTMLElement, spec: ReportSpec): Enhancement {
  target.innerHTML = renderReport(spec);
  target.removeAttribute("aria-busy");
  return enhance(target, createContext(spec, spec.cases || {}));
}
