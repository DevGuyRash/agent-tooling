import { wrapText, textBounds, TextLayout, TextMeasure } from "./text-layout";
import { Annotation, Cell, Meta, Named, Status } from "./model";

export function escapeText(value: string | number): string {
  if (typeof value !== "string" && typeof value !== "number") throw new TypeError("Expected text or a number.");
  if (typeof value === "number" && !Number.isFinite(value)) throw new TypeError("Numbers must be finite; use null for missing observations.");
  return (Object.is(value, -0) ? "-0" : String(value)).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
export function finite(value: number | null | undefined, label: string): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) throw new TypeError(`${label}: expected a finite number or null.`);
  return value;
}
export function numericText(value: number | null | undefined): string {
  return value === null || value === undefined ? "Missing" : escapeText(value);
}
export function documentId(value: string, label = "A presentation ID"): string {
  if (typeof value !== "string" || !/^[A-Za-z][A-Za-z0-9_.:-]*$/.test(value)) throw new TypeError(`${label} must begin with a letter and contain only letters, numbers, underscores, periods, colons or hyphens.`);
  return value;
}
export function identifier(value: string): string { return `<code class="av-id">${escapeText(value)}</code>`; }
type DisplayLabel = string | Named;
/** Keep distinct names concise; repeated rendered names need their supplied identity. */
export function namedLabels(items: Named[]): Map<string, DisplayLabel> {
  const visible = (label: string) => label.replace(/[ \t\n\r\f]+/g, " ").trim();
  const counts = new Map<string, number>();
  for (const item of items) counts.set(visible(item.label), (counts.get(visible(item.label)) || 0) + 1);
  return new Map(items.map(item => [item.id, counts.get(visible(item.label))! > 1 ? item : item.label]));
}
export function labelMarkup(label: DisplayLabel): string {
  return typeof label === "string" ? escapeText(label) : `${escapeText(label.label)} · ${identifier(label.id)}`;
}
function labelText(label: DisplayLabel): string { return typeof label === "string" ? label : `${label.label} · ${label.id}`; }
const statuses: Status[] = ["supported", "conditional", "uncertain", "missing", "failed", "not-applicable"];
export function status(value?: Status): string {
  if (value === undefined) return "";
  if (!statuses.includes(value)) throw new TypeError("Unknown status. Use supported, conditional, uncertain, missing, failed, or not-applicable.");
  return `<span class="av-status av-status-${value}">${escapeText(value.replace(/-/g, " "))}</span>`;
}
/** Links are user-activated references. Unsafe schemes become visible non-links. */
export function evidence(annotation: Annotation): string {
  return (annotation.evidence || []).length ? `<ul class="av-evidence">${annotation.evidence!.map(ref => {
    let safe = false;
    if (ref.href !== undefined) {
      if (/^#[A-Za-z][\w:.-]*$/.test(ref.href)) safe = true;
      else if (/^https?:\/\//i.test(ref.href) && !/[\u0000-\u0020\u007f]/.test(ref.href)) {
        try { const url = new URL(ref.href); safe = !url.username && !url.password; } catch { /* show as plain text */ }
      }
    }
    const label = escapeText(ref.label);
    const link = safe ? `<a href="${escapeText(ref.href!)}" rel="noopener noreferrer">${label}</a>` : label;
    const unavailable = ref.href !== undefined && !safe ? ` <span class="av-muted">(link omitted: ${escapeText(ref.href)})</span>` : "";
    return `<li>${link}${unavailable}${ref.note ? ` — ${escapeText(ref.note)}` : ""}</li>`;
  }).join("")}</ul>` : "";
}
export function annotation(value: Annotation): string {
  return `${value.note ? `<p class="av-note">${escapeText(value.note)}</p>` : ""}${evidence(value)}`;
}
export function cell(value: Cell): string {
  return `${value.value === null ? '<span class="av-missing">Missing</span>' : escapeText(value.value)}${status(value.status)}${annotation(value)}`;
}
export type FrameKind = "evidence" | "comparison" | "quantitative" | "conditions" | "interpretation" | "provenance" | "artifacts" | "uncertainty" | "history";
export function card(meta: Meta, body: string, kind: FrameKind = "evidence"): string {
  if (meta.collapsible !== undefined && typeof meta.collapsible !== "boolean") throw new TypeError("collapsible must be true or false.");
  if (meta.open !== undefined && typeof meta.open !== "boolean") throw new TypeError("open must be true or false.");
  const identity = meta.id === undefined ? "" : ` id="${escapeText(documentId(meta.id))}"`;
  const context = annotation(meta), limits = meta.limitations?.length ? `<aside class="av-limits"><h3>Limitations</h3><ul>${meta.limitations.map(x => `<li>${escapeText(x)}</li>`).join("")}</ul></aside>` : "";
  const heading = `<h2 class="av-card-title">${escapeText(meta.title)}</h2>`;
  const description = meta.description ? `<p class="av-frame-description">${escapeText(meta.description)}</p>` : "";
  const controls = `<div class="av-frame-tools av-enhance-only" data-av-controls hidden><button type="button" class="av-button" data-av-focus title="Expand" aria-label="Expand ${escapeText(meta.title)}"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5"/></svg><span class="av-sr-only">Expand</span></button></div>`;
  const content = `<div class="av-frame-content">${description}<div class="av-frame-body">${body}</div>${context || limits ? `<footer class="av-frame-footer">${context}${limits}</footer>` : ""}</div>`;
  return meta.collapsible === false
    ? `<section class="av-card av-frame av-frame-${kind}" data-av-frame="${kind}"${identity}><header class="av-card-header">${heading}${controls}</header>${content}</section>`
    : `<details class="av-card av-frame av-frame-${kind}" data-av-frame="${kind}"${identity} data-av-section${meta.open === false ? "" : " open"}><summary class="av-card-header">${heading}${controls}</summary>${content}</details>`;
}
export function table(caption: string, headers: DisplayLabel[], rows: string[][]): string {
  return `<div class="av-table-scroll" tabindex="0" role="region" aria-label="${escapeText(caption)}"><table><caption class="av-sr-only">${escapeText(caption)}</caption><thead><tr>${headers.map(h => `<th scope="col">${labelMarkup(h)}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map(row => `<tr>${row.map((c, i) => i === 0 ? `<th scope="row">${c}</th>` : `<td>${c}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${Math.max(1, headers.length)}">No observations supplied.</td></tr>`}</tbody></table></div>`;
}
export function dataTable(title: string, headers: string[], rows: string[][]): string {
  return `<details class="av-data" data-av-content-view="data"><summary>Data and annotations</summary>${table(title, headers, rows)}</details>`;
}
/** Enhancement hooks are scoped to an explorer; no data value becomes a selector or DOM ID. */
/** Occurrence labels distinguish repeated names without inventing stable entity IDs.
 * Prefix the complete set when needed, so authored labels cannot collide with a
 * generated suffix. The number describes supplied order only, not a ranking. */
export function occurrenceLabels(items: readonly { label: string }[], noun: string): string[] {
  const labels = items.map(item => item.label);
  const visible = labels.map(label => label.replace(/[ \t\n\r\f]+/g, " ").trim());
  return new Set(visible).size === visible.length ? labels : labels.map((label, index) => `${noun} ${index + 1} · ${label}`);
}
export function explorerControls(label: string, objects: { key: string; label: DisplayLabel }[]): string {
  return objects.length > 1 ? `<div class="av-explorer-tools av-enhance-only" data-av-controls hidden><label class="av-field"><span>${escapeText(label)}</span><select data-av-select><option value="">Choose an item</option>${objects.map(object => `<option value="${escapeText(object.key)}">${escapeText(labelText(object.label))}</option>`).join("")}</select></label></div>` : "";
}
export function objectDetail(key: string, label: DisplayLabel, body: string, open = false, className = ""): string {
  return `<details class="av-object-detail${className ? ` ${escapeText(className)}` : ""}" data-av-object="${escapeText(key)}"${open ? " open" : ""}><summary>${labelMarkup(label)}</summary><div class="av-object-body">${body}</div></details>`;
}
export function named(items: Named[], label: string): Map<string, Named> {
  const result = new Map<string, Named>();
  for (const item of items) {
    if (typeof item.id !== "string" || !item.id || result.has(item.id)) throw new TypeError(`${label}: IDs must be nonempty and unique.`);
    escapeText(item.label);
    result.set(item.id, item);
  }
  return result;
}
export function axisLabel(label: string, unit?: string): string { return unit ? `${label} (${unit})` : label; }
export const palette = ["var(--av-series-1, #006b69)", "var(--av-series-2, #9d431f)", "var(--av-series-3, #56449b)", "var(--av-series-4, #196aa1)", "var(--av-series-5, #8b356a)", "var(--av-series-6, #57651b)"];
export interface Scale { min: number; max: number; map: (n: number) => number; ticks: number[]; tickLabels: string[]; offset: number | null }
/** Direct finite differences preserve narrow domains; normalization is only an overflow fallback. */
export function scale(values: number[], start: number, end: number): Scale | null {
  if (!values.length) return null;
  let min = values[0], max = values[0];
  for (const n of values) { finite(n, "Scale"); min = Math.min(min, n); max = Math.max(max, n); }
  const magnitude = Math.max(Math.abs(min), Math.abs(max)) || 1;
  const low = min / magnitude, high = max / magnitude;
  const span = max - min, direct = Number.isFinite(span);
  const ratio = (n: number) => min === max ? 0.5 : direct ? (n - min) / span : (n / magnitude - low) / (high - low);
  // Fractional ticks can round to the same representable number in a narrow domain.
  const ticks = [...new Set(min === max ? [min] : [min, ...[0.25, 0.5, 0.75].map(t => direct ? min + span * t : (low * (1 - t) + high * t) * magnitude), max])];
  const compact = ticks.map(n => numericLabel(n, 4));
  // An explicit additive offset keeps close-value ticks short and distinguishable.
  const offset = new Set(compact).size < ticks.length && direct ? min : null;
  const displayValues = ticks.map(n => offset === null ? n : n - offset);
  let precision = 4;
  while (precision < 17 && new Set(displayValues.map(n => numericLabel(n, precision))).size < ticks.length) precision++;
  return { min, max, map: n => start + ratio(n) * (end - start), ticks, tickLabels: displayValues.map(n => numericLabel(n, precision)), offset };
}
function numericLabel(n: number, precision: number): string {
  const [mantissa, exponent] = n.toPrecision(precision).split("e");
  const compact = mantissa.includes(".") ? mantissa.replace(/0+$/, "").replace(/\.$/, "") : mantissa;
  return compact + (exponent === undefined ? "" : `e${exponent}`);
}
function axisBlock(layout: TextLayout, x: number, top: number, anchor = "middle", title = layout.text): string {
  return `<text x="${x}" y="${top + layout.fontSize}" text-anchor="${anchor}" xml:space="preserve"><title>${escapeText(title)}</title>${layout.lines.map((line, i) => `<tspan x="${x}" y="${top + layout.fontSize + i * layout.lineHeight}">${escapeText(line)}</tspan>`).join("")}</text>`;
}
function axisText(value: string, x: number, top: number, width: number, measure?: TextMeasure, anchor = "middle"): string {
  return axisBlock(wrapText(value, { maxWidth: width, fontSize: 14, lineHeight: 21, measure }), x, top, anchor);
}
interface HorizontalTick { value: number; x: number; anchor: "start" | "middle" | "end"; text: TextLayout; top: number }
export function horizontalAxisLayout(s: Scale, label: string, measure?: TextMeasure): { ticks: HorizontalTick[]; label: TextLayout; labelTop: number; offset: TextLayout | null; offsetTop: number; center: number; height: number } {
  const left = Math.min(s.map(s.min), s.map(s.max)), right = Math.max(s.map(s.min), s.map(s.max));
  const available = right === left ? 80 : Math.max(24, right - left), center = (left + right) / 2;
  const ticks: HorizontalTick[] = s.ticks.map((value, index) => {
    const x = s.map(value), anchor = s.ticks.length === 1 ? "middle" : x === left ? "start" : x === right ? "end" : "middle";
    const width = anchor === "middle" && s.ticks.length > 1 ? Math.max(24, Math.min(available, 2 * Math.min(x - left, right - x))) : available;
    return { value, x, anchor, text: wrapText(s.tickLabels[index], { maxWidth: width, fontSize: 14, lineHeight: 21, measure }), top: 0 };
  });
  const lanes: { right: number; height: number; ticks: HorizontalTick[] }[] = [];
  for (const tick of [...ticks].sort((a, b) => a.x - b.x)) {
    const box = textBounds(tick.text, { x: tick.x, y: 0, anchor: tick.anchor });
    let lane = lanes.find(item => item.right + 8 <= box.x);
    if (!lane) { lane = { right: -Infinity, height: 0, ticks: [] }; lanes.push(lane); }
    lane.right = box.x + box.width; lane.height = Math.max(lane.height, tick.text.height); lane.ticks.push(tick);
  }
  let top = 9;
  for (const lane of lanes) { for (const tick of lane.ticks) tick.top = top; top += lane.height + 4; }
  const labelTop = top + 5, labelBlock = wrapText(label, { maxWidth: available, fontSize: 14, lineHeight: 21, measure });
  const offsetTop = labelTop + labelBlock.height + 4;
  const offset = s.offset === null ? null : wrapText(`Add ${s.offset} to tick labels`, { maxWidth: available, fontSize: 14, lineHeight: 21, measure });
  return { ticks, label: labelBlock, labelTop, offset, offsetTop, center, height: (offset ? offsetTop + offset.height : labelTop + labelBlock.height) + 10 };
}
export function xAxis(s: Scale, y: number, label: string, measure?: TextMeasure): string {
  const layout = horizontalAxisLayout(s, label, measure);
  return `<line class="av-axis" x1="${s.map(s.min)}" x2="${s.map(s.max)}" y1="${y}" y2="${y}"/>${layout.ticks.map(tick => `<g class="av-axis-tick"><line class="av-axis" x1="${tick.x}" x2="${tick.x}" y1="${y}" y2="${y + 5}"/>${axisBlock(tick.text, tick.x, y + tick.top, tick.anchor, `Value: ${tick.value}`)}</g>`).join("")}${axisBlock(layout.label, layout.center, y + layout.labelTop)}${layout.offset ? axisBlock(layout.offset, layout.center, y + layout.offsetTop) : ""}`;
}
export function yAxis(s: Scale, x: number, label: string, measure?: TextMeasure, right = 850): string {
  return `${s.ticks.map((v, i) => `<g><line class="av-grid" x1="${x}" x2="${right}" y1="${s.map(v)}" y2="${s.map(v)}"/><text x="${x - 9}" y="${s.map(v) + 4}" text-anchor="end"><title>Value: ${escapeText(v)}</title>${escapeText(s.tickLabels[i])}</text></g>`).join("")}${axisText(label, x, 4, Math.max(100, right - x), measure, "start")}${s.offset === null ? "" : axisText(`Add ${s.offset} to tick labels`, x, 27 + wrapText(label, { maxWidth: Math.max(100, right - x), measure }).height, Math.max(100, right - x), measure, "start")}`;
}
export function svg(title: string, height: number, content: string, width = 900): string {
  return `<div class="av-plot-shell" data-av-plot data-av-figure data-av-figure-title="${escapeText(title)}" data-av-content-view="visual"><div class="av-plot-toolbar av-enhance-only" data-av-controls hidden><span class="av-sr-only">Plot size</span><div class="av-button-group"><button type="button" class="av-button" data-av-zoom-out aria-label="Zoom out ${escapeText(title)}">−</button><button type="button" class="av-button" data-av-zoom-reset title="Reset zoom and fit chart">Reset</button><button type="button" class="av-button" data-av-zoom-in aria-label="Zoom in ${escapeText(title)}">+</button></div></div><div class="av-plot-scroll" tabindex="0" role="region" aria-label="${escapeText(title)} plot"><svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="${content.includes("data-av-inspect=") ? "group" : "img"}" data-av-zoom-target aria-label="${escapeText(title)}; exact values and annotations in the following data table"><title>${escapeText(title)}</title>${content}</svg></div></div>`;
}
export function noPlot(): string { return '<p class="av-empty">No complete numeric observations to plot. Supplied entries and missing values are retained in the data table.</p>'; }
