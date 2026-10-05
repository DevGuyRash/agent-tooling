/** Browser behavior for a rendered report: theme, section index, the run
 * drawer, ledger filtering and sorting, arm highlighting and diagrams. Every
 * view is complete without it; this only adds ways to move through the data. */
import { esc, fmtNum, fmtSeconds, inline, isNum, outcomeBadge, outcomeLabel, outcomeMark } from "./core";
import { attachMermaid, DiagramController } from "./mermaid";
import { createContext, RenderContext, ReportSpec } from "./model";
import { renderReport } from "./report";
import { judgeQuestion, outcomeOf, recordPath, TrialReport } from "./trial-model";

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

export interface Enhancement { cleanup(): void; diagrams?: DiagramController }

/** Add behavior to a rendered report. `ctx` supplies the trial runs for the drawer. */
export function enhance(root: HTMLElement, ctx?: RenderContext): Enhancement {
  const doc = root.ownerDocument, win = doc.defaultView!;
  const report = root.matches("[data-av-report]") ? root : root.querySelector<HTMLElement>("[data-av-report]") || root;
  const offs: Array<() => void> = [];
  const on = <K extends keyof HTMLElementEventMap>(el: EventTarget, type: K | string, fn: (e: any) => void, opts?: AddEventListenerOptions) => { el.addEventListener(type, fn, opts); offs.push(() => el.removeEventListener(type, fn, opts)); };

  // Theme -------------------------------------------------------------
  const toggle = report.querySelector<HTMLButtonElement>("[data-av-theme-toggle]");
  if (toggle) {
    const show = (t: Theme) => { toggle.setAttribute("data-theme-choice", t); toggle.querySelector(".av-theme-word")!.textContent = t === "auto" ? "Auto" : t === "light" ? "Light" : "Dark"; toggle.setAttribute("aria-label", `Color theme: ${t === "auto" ? "follows the system" : t}. Select to change.`); };
    show(storedTheme()); toggle.hidden = false;
    on(toggle, "click", () => { const next = themes[(themes.indexOf(storedTheme()) + 1) % themes.length]; applyTheme(doc, next); show(next); diagrams?.refresh(); });
  }

  // Section index: the current section is the last whose top has passed a
  // line a third of the way down the window; above the first, none is current.
  const links = Array.from(report.querySelectorAll<HTMLAnchorElement>(".av-toc a"));
  const sections = links.map(a => doc.getElementById(decodeURIComponent(a.hash.slice(1)))).filter((s): s is HTMLElement => !!s);
  const bar = report.querySelector<HTMLElement>(".av-topbar");
  let spyQueued = false;
  const spy = () => {
    spyQueued = false;
    const line = win.innerHeight * 0.33;
    let current: HTMLElement | undefined;
    for (const s of sections) if (s.getBoundingClientRect().top <= line) current = s;
    for (const a of links) {
      const on = !!current && a.hash === "#" + current.id;
      if (on !== a.hasAttribute("aria-current")) { a.toggleAttribute("aria-current", on); if (on) a.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }
    }
    bar?.toggleAttribute("data-scrolled", win.scrollY > 8);
  };
  const queue = () => { if (!spyQueued) { spyQueued = true; win.requestAnimationFrame ? win.requestAnimationFrame(spy) : spy(); } };
  on(win, "scroll", queue, { passive: true }); on(win, "resize", queue); spy();

  // Wide content: fade the edge that has more to scroll to, so a clipped table
  // or grid announces that it continues.
  const scrollers = Array.from(report.querySelectorAll<HTMLElement>(".av-scroll-x"));
  const edge = (el: HTMLElement) => {
    const x = el.scrollWidth - el.clientWidth > 2, y = el.scrollHeight - el.clientHeight > 2;
    el.toggleAttribute("data-more-right", x && el.scrollLeft < el.scrollWidth - el.clientWidth - 2);
    el.toggleAttribute("data-more-left", x && el.scrollLeft > 2);
    el.toggleAttribute("data-more-down", y && el.scrollTop < el.scrollHeight - el.clientHeight - 2);
  };
  for (const el of scrollers) { on(el, "scroll", () => edge(el), { passive: true }); edge(el); }
  on(win, "resize", () => scrollers.forEach(edge));

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

  // Ledger ----------------------------------------------------------------
  for (const block of Array.from(report.querySelectorAll<HTMLElement>(".av-ledger")).map(t => t.closest<HTMLElement>(".av-block")!).filter(Boolean)) {
    const tools = block.querySelector<HTMLElement>("[data-av-ledger-tools]"), table = block.querySelector<HTMLTableElement>("table.av-ledger")!;
    const rows = Array.from(table.tBodies[0].rows), count = block.querySelector<HTMLOutputElement>(".av-ledger-count");
    if (!tools) continue;
    tools.hidden = false;
    let outcome = "";
    const apply = () => {
      const arm = tools.querySelector<HTMLSelectElement>('[data-filter="arm"]')!.value, cs = tools.querySelector<HTMLSelectElement>('[data-filter="case"]')!.value;
      const q = tools.querySelector<HTMLInputElement>('[data-filter="text"]')!.value.trim().toLowerCase();
      let n = 0;
      for (const r of rows) {
        const ok = (!outcome || r.dataset.outcome === outcome) && (!arm || r.dataset.arm === arm) && (!cs || r.dataset.case === cs) && (!q || (r.textContent || "").toLowerCase().includes(q));
        r.hidden = !ok; if (ok) n++;
      }
      if (count) count.textContent = `${n} of ${rows.length} runs`;
    };
    tools.querySelectorAll<HTMLButtonElement>("[data-outcome]").forEach(b => on(b, "click", () => {
      outcome = b.dataset.outcome || "";
      tools.querySelectorAll("[data-outcome]").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
      apply();
    }));
    tools.querySelectorAll("select,input").forEach(el => on(el, "input", apply));
    table.querySelectorAll<HTMLTableCellElement>("th[data-sortable]").forEach((th, col) => {
      const index = Array.from(th.parentElement!.children).indexOf(th);
      th.tabIndex = 0; th.setAttribute("aria-sort", "none");
      const sort = () => {
        const dir = th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending";
        table.querySelectorAll("th[data-sortable]").forEach(x => x.setAttribute("aria-sort", "none"));
        th.setAttribute("aria-sort", dir);
        const num = th.dataset.sortable === "num";
        const key = (r: HTMLTableRowElement) => { const c = r.cells[index]; const raw = c?.dataset.sort ?? c?.textContent ?? ""; return num ? parseFloat(raw) || 0 : raw.trim().toLowerCase(); };
        rows.sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) * (dir === "ascending" ? 1 : -1); });
        rows.forEach(r => table.tBodies[0].appendChild(r));
      };
      on(th, "click", sort); on(th, "keydown", (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
      void col;
    });
    apply();
  }

  // Run drawer --------------------------------------------------------------
  const dialog = report.querySelector<HTMLDialogElement>("[data-av-drawer]");
  const data = ctx?.trial;
  let currentRun = -1;
  const sequence = (): number[] => {
    const rows = Array.from(report.querySelectorAll<HTMLElement>("table.av-ledger tbody tr")).filter(r => !r.hidden).map(r => Number(r.dataset.run));
    return rows.length ? rows : (data?.runs || []).map((_, i) => i);
  };
  const openRun = (i: number, opener?: HTMLElement) => {
    if (!dialog || !data || !ctx || !data.runs[i]) return;
    currentRun = i;
    dialog.querySelector<HTMLElement>("[data-av-drawer-body]")!.innerHTML = drawerHtml(data, i, ctx, sequence());
    if (!dialog.open) { (dialog as any).__opener = opener; typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", ""); }
    dialog.querySelector<HTMLElement>(".av-drawer-close")?.focus();
  };
  if (dialog && data && ctx) {
    on(report, "click", (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (dialog.contains(t)) {
        const nav = t.closest<HTMLElement>("[data-av-nav]");
        if (nav) { const seq = sequence(), at = seq.indexOf(currentRun), next = seq[(at + (nav.dataset.avNav === "next" ? 1 : -1) + seq.length) % seq.length]; openRun(next); }
        else if (t.closest(".av-drawer-close") || t === dialog) dialog.close();
        else if (t.closest("[data-av-copy]")) { const text = t.closest<HTMLElement>("[data-av-copy]")!.dataset.avCopy || ""; try { void win.navigator.clipboard?.writeText(text); t.closest<HTMLElement>("[data-av-copy]")!.textContent = "Copied"; } catch { /* clipboard may be refused */ } }
        return;
      }
      const run = t.closest<HTMLElement>("[data-run]");
      if (run && report.contains(run)) openRun(Number(run.dataset.run), run);
    });
    on(report, "keydown", (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (dialog.open && (e.key === "ArrowRight" || e.key === "ArrowLeft") && dialog.contains(t)) {
        e.preventDefault(); const seq = sequence(), at = seq.indexOf(currentRun); openRun(seq[(at + (e.key === "ArrowRight" ? 1 : -1) + seq.length) % seq.length]);
      } else if (e.key === "Enter" && t.matches("tr[data-run]")) { e.preventDefault(); openRun(Number(t.dataset.run), t); }
    });
    on(dialog, "close", () => { const opener = (dialog as any).__opener as HTMLElement | undefined; opener?.focus?.(); });
  }

  // Diagrams --------------------------------------------------------------
  let diagrams: DiagramController | undefined;
  if (report.querySelector("[data-av-mermaid]")) { diagrams = attachMermaid(report, () => undefined); void diagrams.refresh(); }
  // Diagrams read theme colors when drawn; redraw when the system theme flips.
  const media = win.matchMedia?.("(prefers-color-scheme: dark)");
  if (media && diagrams) on(media, "change", () => { void diagrams?.refresh(); });

  report.setAttribute("data-av-ready", "");
  const Ev = win.Event; doc.dispatchEvent(new Ev("av-report-ready"));
  return { diagrams, cleanup() { offs.splice(0).forEach(f => f()); diagrams?.cleanup(); report.removeAttribute("data-av-ready"); } };
}

function drawerHtml(data: TrialReport, i: number, ctx: RenderContext, seq: number[]): string {
  const r = data.runs[i], o = outcomeOf(r), at = seq.indexOf(i);
  const scenario = (data.plan?.scenarios || []).find(s => s.name === r.scenario);
  const required = new Set(scenario?.required || []);
  const caseName = ctx.caseLabels[r.scenario] || r.scenario;
  const facts: Array<[string, string]> = [
    ["Status", `<code>${esc(r.status || "")}</code>`],
    ...(o === "invalid" ? [["Invalid because", `<code>${esc(r.invalid_reason || r.status || "unknown")}</code>`] as [string, string]] : []),
    ["Executor time", esc(fmtSeconds(r.seconds))],
    ...(isNum(r.setup_seconds) ? [["Setup", esc(fmtSeconds(r.setup_seconds))] as [string, string]] : []),
    ...(isNum(r.checks_seconds) ? [["Checks", esc(fmtSeconds(r.checks_seconds))] as [string, string]] : []),
    ...(isNum(r.judge_seconds) ? [["Judge", esc(fmtSeconds(r.judge_seconds))] as [string, string]] : []),
    ...(isNum(r.commands) ? [["Commands", esc(fmtNum(r.commands))] as [string, string]] : []),
    ...(r.confined === false ? [["Sandbox", "<strong>unconfined</strong>"] as [string, string]] : []),
    ...(r.artifact_missing ? [["Artifact", "<strong>not produced</strong>"] as [string, string]] : []),
  ];
  const checks = Object.entries(r.checks || {});
  const checkRows = checks.map(([k, v]) => {
    const val = typeof v === "boolean" ? `${outcomeMark(v ? "pass" : "fail")}<span>${v ? "true" : "false"}</span>` : `<code>${esc(typeof v === "string" ? v : JSON.stringify(v))}</code>`;
    return `<tr${required.has(k) ? ' class="av-req"' : ""}><th scope="row"><code>${esc(k)}</code>${required.has(k) ? ' <span class="av-chip av-chip--req">required</span>' : ""}</th><td>${val}</td></tr>`;
  }).join("");
  const usage = Object.entries(r.usage || {}).filter(([, v]) => isNum(v) && v !== 0);
  const path = recordPath(data, r);
  const q = judgeQuestion(scenario);
  return `<header class="av-drawer-head"><div><p class="av-eyebrow">Run ${at + 1} of ${seq.length}${seq.length !== data.runs.length ? " shown" : ""} · <code>${esc(r.job || "")}</code></p><h2 id="av-drawer-title" class="av-drawer-title">${esc(caseName)}</h2><p class="av-drawer-sub">${ctx.arms.tag(r.arm)}<span>repeat ${esc(r.repeat ?? "?")}</span>${outcomeBadge(o)}</p></div><button type="button" class="av-drawer-close" aria-label="Close run record">✕</button></header>
<div class="av-drawer-scroll">
<dl class="av-facts av-facts--tight">${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join("")}</dl>
${r.judge ? `<section class="av-drawer-sec"><h3>Judge <span class="av-judge av-judge--${esc(r.judge.verdict || "none")}">${esc(r.judge.verdict || "no verdict")}</span></h3>${r.judge.reason ? `<p class="av-drawer-text">${inline(r.judge.reason)}</p>` : ""}${q ? `<details class="av-drawer-q"><summary>Question the judge answered</summary><p class="av-drawer-text">${esc(q)}</p></details>` : ""}</section>` : ""}
${checks.length ? `<section class="av-drawer-sec"><h3>Checks</h3><table class="av-table av-table--compact"><tbody>${checkRows}</tbody></table></section>` : ""}
${r.final_message_excerpt ? `<section class="av-drawer-sec"><h3>Final output${r.final_message_excerpt.length >= 2000 ? ' <span class="av-muted">· first 2,000 characters; the full text is in the native record</span>' : ""}</h3><pre class="av-pre av-pre--tall">${esc(r.final_message_excerpt)}</pre></section>` : ""}
${usage.length ? `<section class="av-drawer-sec"><h3>Usage</h3><dl class="av-facts av-facts--tight">${usage.map(([k, v]) => `<div><dt><code>${esc(k)}</code></dt><dd class="av-num">${esc(fmtNum(v))}</dd></div>`).join("")}</dl></section>` : ""}
${path ? `<section class="av-drawer-sec"><h3>Native record</h3><p class="av-drawer-path"><code>${esc(path)}</code><button type="button" class="av-btn av-btn--small" data-av-copy="${esc(path)}">Copy path</button></p><p class="av-muted">The full transcript, events, checks and judge prompt live in this directory.</p></section>` : ""}
</div>
<footer class="av-drawer-foot"><button type="button" class="av-btn" data-av-nav="prev">← Previous</button><span class="av-muted">${esc(outcomeLabel[o])} · ← → to move</span><button type="button" class="av-btn" data-av-nav="next">Next →</button></footer>`;
}

/** Render a specification into a target and enhance it. */
export function mount(target: HTMLElement, spec: ReportSpec): Enhancement {
  target.innerHTML = renderReport(spec);
  target.removeAttribute("aria-busy");
  return enhance(target, createContext(spec, spec.cases || {}));
}
