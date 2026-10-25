/** DOM-free helpers shared by every view: escaping, identifiers, formatting,
 * interval arithmetic and the run-outcome vocabulary. Every renderer returns a
 * string, so the same code runs in a browser or under Node. */

export function escapeText(value: string | number): string {
  if (typeof value !== "string" && typeof value !== "number") throw new TypeError("Expected text or a number.");
  if (typeof value === "number" && !Number.isFinite(value)) throw new TypeError("Numbers must be finite; use null for missing observations.");
  return (Object.is(value, -0) ? "-0" : String(value)).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}

/** Escape anything a data file can hold; missing values become empty text. */
export function esc(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isFinite(value) ? escapeText(value) : "";
  if (typeof value === "string") return escapeText(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  try { return escapeText(JSON.stringify(value) ?? ""); } catch { return ""; }
}

export function documentId(value: string, label = "A presentation ID"): string {
  if (typeof value !== "string" || !/^[A-Za-z][A-Za-z0-9_.:-]*$/.test(value)) throw new TypeError(`${label} must begin with a letter and contain only letters, numbers, underscores, periods, colons or hyphens.`);
  return value;
}

/** A short, stable digest (FNV-1a) for identifiers derived from arbitrary names. */
export function hash(value: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) { h ^= value.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(36);
}

/** An element id for any name: readable where the name allows, unique by digest. */
export function slug(value: string, prefix = "av"): string {
  const base = String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  return `${prefix}-${base || "x"}-${hash(String(value))}`;
}

/** Whitespace, one explicit set for both checkers and every view: ASCII space and tab, line breaks, and all Unicode
 * whitespace (no-break and em spaces, the byte-order mark, next-line and the information separators among them). */
export const WHITESPACE = "\t\n\u000b\f\r \u001c\u001d\u001e\u001f\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff";
/** Whether text says nothing: whitespace alone (WHITESPACE), or nothing. The one blank test of both checkers and every
 * view: a reading, a story part, a description, a title or an id is blank exactly when this says so. */
export const blank = (v: string): boolean => [...v].every(ch => WHITESPACE.includes(ch));
/** Text with WHITESPACE removed from both ends: how every view trims what it shows. */
export function stripText(v: string): string {
  let i = 0, j = v.length;
  while (i < j && WHITESPACE.includes(v[i])) i++;
  while (j > i && WHITESPACE.includes(v[j - 1])) j--;
  return v.slice(i, j);
}
/** Whether a value says something: text, or a list holding text, that is not blank. */
export const said = (v: unknown): boolean => (typeof v === "string" && !blank(v)) || (Array.isArray(v) && v.some(x => typeof x === "string" && !blank(x)));
const WS_CLASS = [...WHITESPACE].map(ch => `\\u${ch.charCodeAt(0).toString(16).padStart(4, "0")}`).join("");
/** A run of WHITESPACE, for collapsing it to one space. */
export const WS_RUN = new RegExp(`[${WS_CLASS}]+`, "g");
/** A date as written: a day YYYY-MM-DD, then optionally "T" or a space and a time HH:MM, then optionally :SS and a
 * fraction, then optionally Z or an offset ±HH:MM. */
const DATE_TEXT = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?$/;
const pad = (n: number, width: number) => String(n).padStart(width, "0");
/** A date as every view and both checks read one: WHITESPACE padding aside, DATE_TEXT naming a real calendar day and,
 * when a time follows, a real time (hours to 23, minutes and seconds to 59, offset hours to 23 and minutes to 59; no
 * zone is UTC). A day alone is that calendar day, with no time. A day with a time is the instant it names: `time` is
 * that instant (ms) and `day` its day in UTC, so the day, the order and the time shown agree. The day must fall within
 * 0001-01-01 and 9999-12-31; anything else is null. */
export function readDate(v: unknown): { day: string; time: number | null } | null {
  const m = typeof v === "string" ? DATE_TEXT.exec(stripText(v)) : null;
  if (!m) return null;
  const [y, mo, d] = [m[1], m[2], m[3]].map(Number);
  // setUTCFullYear, not Date.UTC, which reads years 0-99 as 1900-1999.
  const at = new Date(0);
  at.setUTCFullYear(y, mo - 1, d);
  if (y < 1 || at.getUTCFullYear() !== y || at.getUTCMonth() !== mo - 1 || at.getUTCDate() !== d) return null;
  if (m[4] === undefined) return { day: `${m[1]}-${m[2]}-${m[3]}`, time: null };
  const [h, mi, s] = [m[4], m[5], m[6] ?? "0"].map(Number);
  const zone = m[8] && m[8] !== "Z" ? m[8] : "";
  const [zh, zm] = zone ? [Number(zone.slice(1, 3)), Number(zone.slice(4))] : [0, 0];
  if (h > 23 || mi > 59 || s > 59 || zh > 23 || zm > 59) return null;
  const offset = (zone.startsWith("-") ? -1 : 1) * (zh * 60 + zm);
  const time = at.getTime() + ((h * 60 + mi - offset) * 60 + s) * 1000 + Number((m[7] ?? ".").slice(1).padEnd(3, "0").slice(0, 3));
  const u = new Date(time), uy = u.getUTCFullYear();
  return uy < 1 || uy > 9999 ? null : { day: `${pad(uy, 4)}-${pad(u.getUTCMonth() + 1, 2)}-${pad(u.getUTCDate(), 2)}`, time };
}
/** A number written as text, padded with any WHITESPACE: both checkers and every view read numeric text by this. */
export const NUMERIC_TEXT = new RegExp(`^[${WS_CLASS}]*-?(\\d+\\.?\\d*|\\.\\d+)([eE][-+]?\\d+)?[${WS_CLASS}]*$`);
/** The number numeric text writes, its WHITESPACE padding removed first (Number alone knows a different set). */
export const numberOf = (text: string): number => Number(stripText(text));
/** A blank line between paragraphs: a line break, any WHITESPACE, a line break. */
const PARAGRAPH_BREAK = new RegExp(`\\n[${WS_CLASS}]*\\n`);
/** An identifier: text with something in it that starts with no "$" (kept for notes) and has no whitespace at either
 * end. Every check of every kind of data holds each id to this, so every view compares ids exactly as written. */
export const isId = (v: unknown): v is string => typeof v === "string" && v !== "" && !v.startsWith("$") && !WHITESPACE.includes(v[0]) && !WHITESPACE.includes(v[v.length - 1]);
/** The entries of a keyed map in data, in its own order, as every check and every view lists them: a trial's pairwise
 * judgments, a judgment's counts by case, a plan's arms, a run's checks and usage, a total's level counts, an
 * alternative's attributes, a criterion's scores, and a narrative's or story's records. A key starting with "$" is a
 * note, not an entry, for every check and every view alike. */
export function entriesOf<T>(map: { [key: string]: T } | null | undefined): Array<[string, T]>;
export function entriesOf(map: unknown): Array<[string, unknown]>;
export function entriesOf(map: unknown): Array<[string, unknown]> {
  if (!map || typeof map !== "object" || Array.isArray(map)) return [];
  return Object.keys(map).filter(k => !k.startsWith("$")).map(k => [k, (map as Record<string, unknown>)[k]]);
}
/** The keys entriesOf lists. */
export const keysIn = (map: unknown): string[] => entriesOf(map).map(e => e[0]);
/** The values entriesOf lists. */
export function valuesIn<T>(map: { [key: string]: T } | null | undefined): T[];
export function valuesIn(map: unknown): unknown[];
export function valuesIn(map: unknown): unknown[] { return entriesOf(map).map(e => e[1]); }

export type AttrValue = string | number | boolean | null | undefined;
/** Attribute text; false, null and undefined omit the attribute, true writes it bare. */
export function attrs(map: Record<string, AttrValue>): string {
  let out = "";
  for (const [name, value] of Object.entries(map)) {
    if (value === false || value === null || value === undefined) continue;
    out += value === true ? ` ${name}` : ` ${name}="${esc(value)}"`;
  }
  return out;
}

/** A scrollable plot shell. Mermaid output and wide figures render inside it. */
export function svg(title: string, height: number, content: string, width = 900, fit: "width" | "natural" = "width"): string {
  return `<div class="av-plot-shell" data-av-plot data-av-figure${fit === "natural" ? ' data-av-fit-policy="natural"' : ""} data-av-figure-title="${escapeText(title)}"><div class="av-plot-scroll" tabindex="0" role="region" aria-label="${escapeText(title)}"><svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" data-av-zoom-target aria-label="${escapeText(title)}"><title>${escapeText(title)}</title>${content}</svg></div></div>`;
}

// ------------------------------------------------------------- numbers

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
/** A finite number or null: data files are untrusted, so counts are coerced before they reach markup. */
export const num = (v: unknown): number | null => isNum(v) ? v : null;
/** A non-negative whole count, or 0. */
export const count = (v: unknown): number => isNum(v) && v > 0 ? Math.floor(v) : 0;

export function fmtInt(n: number | null | undefined): string {
  return isNum(n) ? Math.round(n).toLocaleString("en-US") : "—";
}

export function fmtPct(p: number | null | undefined, digits = 0): string {
  return isNum(p) ? `${(p * 100).toFixed(digits)}%` : "—";
}

/** Compact magnitude: 0.004, 0.42, 7.5, 312, 4.2k, 1.3M. */
export function fmtNum(x: number | null | undefined): string {
  if (!isNum(x)) return "—";
  const a = Math.abs(x);
  if (a === 0) return "0";
  if (a >= 1e6) return `${(x / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`;
  if (a >= 1e4) return `${(x / 1e3).toFixed(0)}k`;
  if (a >= 1e3) return `${(x / 1e3).toFixed(1)}k`;
  if (a >= 100) return x.toFixed(0);
  if (a >= 10) return x.toFixed(1).replace(/\.0$/, "");
  if (a >= 1) return x.toFixed(2).replace(/\.?0+$/, "");
  return x.toPrecision(2).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

/** A duration in words: seconds under a minute ("52.2 s"), otherwise whole minutes
 * and seconds ("1 min 26 s") or hours and minutes ("2 h 5 min"), never a decimal
 * minute that reads like minutes and seconds. */
export function fmtSeconds(s: number | null | undefined): string {
  if (!isNum(s)) return "—";
  if (Math.abs(s) < 59.95) return `${fmtNum(s)} s`;
  const sign = s < 0 ? "−" : "", t = Math.round(Math.abs(s));
  if (t < 3600) { const m = Math.floor(t / 60), sec = t % 60; return `${sign}${m} min${sec ? ` ${sec} s` : ""}`; }
  const mins = Math.round(t / 60), h = Math.floor(mins / 60), m = mins % 60;
  return `${sign}${h} h${m ? ` ${m} min` : ""}`;
}

/** Seconds in one unit chosen for a whole axis, so ticks never mix units. */
export function secondsUnit(max: number): { div: number; unit: string } {
  return max >= 7200 ? { div: 3600, unit: "h" } : max >= 180 ? { div: 60, unit: "min" } : { div: 1, unit: "s" };
}

export function fmtUsd(x: number | null | undefined): string {
  if (!isNum(x)) return "—";
  if (x === 0) return "$0";
  return Math.abs(x) >= 0.01 ? `$${x.toFixed(2)}` : `$${x.toPrecision(2)}`;
}

/** A signed percentage difference, already in percent units (12.5 → "+13%"). */
export function fmtDelta(pct: number | null | undefined): string {
  if (!isNum(pct)) return "—";
  const r = Math.round(pct);
  return `${r > 0 ? "+" : r < 0 ? "−" : "±"}${Math.abs(r)}%`;
}

/** 95% Wilson score interval for k successes in n trials; null when n is 0. */
export function wilson(k: number, n: number, z = 1.96): [number, number] | null {
  if (!isNum(k) || !isNum(n) || n <= 0) return null;
  const p = k / n, z2 = z * z;
  const centre = p + z2 / (2 * n), spread = z * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)), denom = 1 + z2 / n;
  return [Math.max(0, (centre - spread) / denom), Math.min(1, (centre + spread) / denom)];
}

export function quantile(sorted: number[], q: number): number | null {
  if (!sorted.length) return null;
  const pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

export function median(values: number[]): number | null {
  return quantile(values.filter(isNum).sort((a, b) => a - b), 0.5);
}

export function mean(values: number[]): number | null {
  const v = values.filter(isNum);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

/** Round ticks for an axis that must hold [min, max]: the first tick at or below
 * min and the last at or above max, so the axis ends on a labelled tick and the
 * largest value never sits past the last label. */
export function axisTicks(min: number, max: number, count = 4): number[] {
  const t = niceTicks(min, max, count);
  if (t.length < 2) return t;
  const step = t[1] - t[0];
  while (t[t.length - 1] < max - step * 1e-9) t.push(Number((t[t.length - 1] + step).toPrecision(12)));
  return t;
}

/** Round axis ticks covering [min, max]. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!isNum(min) || !isNum(max)) return [];
  if (min === max) { const pad = Math.abs(min) || 1; min -= pad / 2; max += pad / 2; }
  const raw = (max - min) / Math.max(1, count), mag = 10 ** Math.floor(Math.log10(raw)), err = raw / mag;
  const step = (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1) * mag;
  const ticks: number[] = [];
  for (let t = Math.floor(min / step) * step; t <= max + step * 1e-9; t += step) ticks.push(Number(t.toPrecision(12)));
  return ticks;
}

/** Ticks for a log axis: 1, 2 and 5 times powers of ten inside [lo, hi]. */
export function logTicks(lo: number, hi: number, max = 5): number[] {
  if (!(lo > 0) || !(hi > lo)) return [lo, hi].filter(isNum);
  const out: number[] = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++)
    for (const m of [1, 2, 5]) { const t = m * 10 ** e; if (t >= lo * 0.999 && t <= hi * 1.001) out.push(Number(t.toPrecision(6))); }
  if (out.length <= max) return out.length >= 2 ? out : [lo, hi];
  const decades = out.filter(t => /^1(e|$|0*$)/.test(String(t)) || Math.log10(t) % 1 === 0);
  if (decades.length >= 2 && decades.length <= max) return decades;
  const step = Math.ceil(out.length / max);
  return out.filter((_, i) => i % step === 0);
}

/** A share of a track as a CSS length, clamped to the track. */
export function pos(x: number): string {
  return `${(Math.max(0, Math.min(1, x)) * 100).toFixed(3)}%`;
}

// ------------------------------------------------------------- axes and hover cards

/** One tick on a track: where it sits (a share of the track) and what it reads. */
export interface Tick { x: number; label: string }

/** An axis along a track: a tick mark and label at each tick, a label at either edge turned inward so none leaves the track,
 * and on a narrow track every other label left out (styles: .av-ticks). The view places it beside its axis title. */
export function ticksHtml(ticks: Tick[], o: { top?: boolean } = {}): string {
  const thin = ticks.length >= 5;
  return `<div class="av-ticks${o.top ? " av-ticks--top" : ""}" aria-hidden="true">${ticks.map((t, i) => { const end = t.x <= .03 ? "start" : t.x >= .97 ? "end" : undefined; return `<span class="av-tick"${attrs({ "data-end": end, "data-minor": thin && !end && i % 2 === 1 })} style="--x:${pos(t.x)}">${esc(t.label)}</span>`; }).join("")}</div>`;
}

/** A faint vertical line across a track at each tick, so a mark reads against the axis. */
export const gridlines = (ticks: Tick[]): string => ticks.map(t => `<span class="av-gridline" style="--x:${pos(t.x)}" aria-hidden="true"></span>`).join("");

/** A hover card (enhance.ts draws it): what was tested above, the setup or item it describes beside its mark, then its
 * values as label and value rows, and a closing note. */
export interface Tip { over?: string; title: string; mark?: { shape: string; color: string }; rows?: Array<[string, string]>; note?: string }

/** The attribute that gives a mark its hover card; a row with no value is left out. */
export const tipAttr = (t: Tip): string => ` data-av-tip="${esc(JSON.stringify({ ...t, rows: t.rows?.filter(r => typeof r[1] === "string" && r[1] !== "") }))}"`;

// ------------------------------------------------------------- outcomes

/** The three states a run can end in. Invalid is never a failure. */
export type Outcome = "pass" | "fail" | "invalid";
export const isOutcome = (v: unknown): v is Outcome => v === "pass" || v === "fail" || v === "invalid";
export const outcomeLabel: Record<Outcome, string> = { pass: "Passed", fail: "Failed", invalid: "Invalid" };

/** A run mark: filled for a pass, hollow for a failure, struck through for an
 * invalid run. Shape and fill carry the state; color only reinforces it. */
export function outcomeMark(outcome: Outcome, extra = ""): string {
  const o = isOutcome(outcome) ? outcome : "invalid";
  return `<span class="av-mark av-mark--${o}${extra ? " " + esc(extra) : ""}" aria-hidden="true"></span>`;
}

/** A small pill naming a state in words beside its mark. */
export function outcomeBadge(outcome: Outcome, label?: string): string {
  const o = isOutcome(outcome) ? outcome : "invalid";
  return `<span class="av-badge av-badge--${o}">${outcomeMark(o)}${esc(label ?? outcomeLabel[o])}</span>`;
}

/** Inline-limited text: paragraphs from blank lines, `code`, and **strong**. All
 * other characters are escaped, so supplied text can never become markup. */
// Running text of two or more paragraphs this long flows into columns where its container is wide (styles: .av-flow), each paragraph whole, and
// only where whole paragraphs make two columns of nearly even height: FLOW_EVEN is the taller column's share of the text
// at which two 58ch columns are no taller than one 92ch column. One paragraph, or one that outweighs the rest, keeps one
// column at the reading measure; short text stays one line of thought; and text too long to fit one screen even in
// columns stays one column, so no one reads down and back up again.
const FLOW_MIN = 320, FLOW_MAX = 2400, FLOW_EVEN = 0.6;

export function prose(text: string | string[] | null | undefined, className = "av-prose"): string {
  if (text === null || text === undefined) return "";
  const parts = (Array.isArray(text) ? text : String(text).split(PARAGRAPH_BREAK)).map(s => stripText(String(s))).filter(Boolean);
  if (!parts.length) return "";
  const length = parts.reduce((n, p) => n + p.length, 0);
  let before = 0, taller = 1; // the taller of the two columns whole paragraphs can make, as a share of the text
  for (const p of parts) { before += p.length; taller = Math.min(taller, Math.max(before, length - before) / length); }
  const flow = parts.length > 1 && taller <= FLOW_EVEN && length >= FLOW_MIN && length <= FLOW_MAX ? " av-flow" : "";
  return `<div class="${className}${flow}">${parts.map(p => `<p>${inline(p)}</p>`).join("")}</div>`;
}

export function inline(text: string): string {
  return esc(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}
