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
export function prose(text: string | string[] | null | undefined, className = "av-prose"): string {
  if (text === null || text === undefined) return "";
  const parts = (Array.isArray(text) ? text : String(text).split(/\n\s*\n/)).map(s => String(s).trim()).filter(Boolean);
  if (!parts.length) return "";
  return `<div class="${className}">${parts.map(p => `<p>${inline(p)}</p>`).join("")}</div>`;
}

export function inline(text: string): string {
  return esc(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}
