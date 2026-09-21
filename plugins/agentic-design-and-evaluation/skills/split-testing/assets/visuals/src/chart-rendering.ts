import { exactJson } from './exact-json';
import { ChartContext, CategoryStyle, categoryStyle } from "./categories";
import { Annotation, Meta, Status } from "./model";
import { escapeText as e, Scale, svg, xAxis, horizontalAxisLayout } from "./core";
import { TextLayout, wrapText } from "./text-layout";

export function sceneWidth(context?: ChartContext): number {
  const width = context?.width ?? 900;
  if (!Number.isFinite(width) || width < 240) throw new TypeError("Chart width must be at least 240 CSS pixels.");
  return width;
}
export function labelLayout(text: string, width: number, context?: ChartContext): TextLayout { return wrapText(text, { maxWidth: Math.max(24, width), fontSize: 14, lineHeight: 21, measure: context?.measureText }); }
export function textMarkup(layout: TextLayout, x: number, y: number, anchor = "start", className = ""): string {
  return `<text x="${x}" y="${y + layout.fontSize}" text-anchor="${anchor}" style="font-size:${layout.fontSize}px;white-space:pre"${className ? ` class="${e(className)}"` : ""} xml:space="preserve"><title>${e(layout.text)}</title>${layout.lines.map((line, i) => `<tspan x="${x}" y="${y + layout.fontSize + i * layout.lineHeight}">${e(line)}</tspan>`).join("")}</text>`;
}
export function marker(style: CategoryStyle, x: number, y: number, label: string, size = 5, includeCode = true): string {
  const color = `var(--av-series-${style.color})`, attrs = `fill="${color}" stroke="${color}" stroke-width="1.4"`;
  const title = `<title>${e(label)}</title>`;
  const coded = (shape: string) => includeCode && style.code ? `<g>${shape}<text class="av-category-code" x="${x + size + 4}" y="${y - size}" style="font-size:10px">${e(style.code)}</text></g>` : shape;
  if (style.shape === "circle") return coded(`<circle cx="${x}" cy="${y}" r="${size}" ${attrs}>${title}</circle>`);
  if (style.shape === "square") return coded(`<rect x="${x - size}" y="${y - size}" width="${2 * size}" height="${2 * size}" ${attrs}>${title}</rect>`);
  const points = style.shape === "diamond" ? `${x},${y - size - 1} ${x + size + 1},${y} ${x},${y + size + 1} ${x - size - 1},${y}`
    : style.shape === "triangle" ? `${x},${y - size - 1} ${x + size + 1},${y + size} ${x - size - 1},${y + size}`
    : style.shape === "hexagon" ? `${x - size},${y - size / 2} ${x},${y - size} ${x + size},${y - size / 2} ${x + size},${y + size / 2} ${x},${y + size} ${x - size},${y + size / 2}` : "";
  if (points) return coded(`<polygon points="${points}" ${attrs}>${title}</polygon>`);
  return coded(`<path d="M ${x - size} ${y - size} L ${x + size} ${y + size} M ${x - size} ${y + size} L ${x + size} ${y - size}" fill="none" stroke="${color}" stroke-width="2.3">${title}</path>`);
}
export function markerLegend(id: string, label: string, context?: ChartContext): string {
  const style = categoryStyle(id, context);
  return `<li data-av-category-id="${e(id)}"><svg class="av-marker-key" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">${marker(style, 10, 10, label, 5, false)}</svg><span>${style.code ? `${e(style.code)} · ` : ""}${e(label)}</span></li>`;
}
export interface RowLayout { y: number; top: number; height: number; text: TextLayout }
export function rowsLayout(labels: string[], width: number, context?: ChartContext, minimum = 38): { rows: RowLayout[]; height: number } {
  let top = 8;
  const rows = labels.map(label => { const text = labelLayout(label, width, context), height = Math.max(minimum, text.height + 14); const row = { text, top, y: top + height / 2, height }; top += height; return row; });
  return { rows, height: Math.max(70, top + 8) };
}
export function rowLabelMarkup(row: RowLayout, right = 170): string { return `<g data-av-row-center="${row.y}">${textMarkup(row.text, right, row.y - row.text.height / 2, "end", "av-row-label")}</g>`; }
export function axisHeight(axis: Scale, label: string, context?: ChartContext): number { return horizontalAxisLayout(axis, label, context?.measureText).height; }
export function rowPlot(title: string, height: number, content: string, rowLabels: string, axis: Scale, label: string, context?: ChartContext, labelWidth = 185): string {
  const width = sceneWidth(context), dataWidth = Math.max(80, width - labelWidth), axisH = 6 + axisHeight(axis, label, context);
  const raw = svg(title, height, content, width);
  const toolbar = raw.slice(raw.indexOf('<div class="av-plot-toolbar'), raw.indexOf('<div class="av-plot-scroll'));
  const scene = `<svg xmlns="http://www.w3.org/2000/svg" width="${dataWidth}" height="${height}" viewBox="${labelWidth - 12} 0 ${dataWidth} ${height}" role="${content.includes("data-av-inspect=") ? "group" : "img"}" data-av-zoom-target aria-label="${e(title)}; exact values and annotations in the following data table"><title>${e(title)}</title>${content}</svg>`;
  return `<div class="av-plot-shell av-row-plot" data-av-plot data-av-figure data-av-figure-title="${e(title)}" data-av-content-view="visual" style="--av-axis-row-width:${labelWidth}px">${toolbar}<div class="av-row-plot-layout"><div class="av-axis-corner">${e(label)}</div><div class="av-axis-x-viewport"><svg xmlns="http://www.w3.org/2000/svg" data-av-axis-layer="x" width="${dataWidth}" height="${axisH}" viewBox="${labelWidth - 12} 0 ${dataWidth} ${axisH}" role="img" aria-label="${e(label)} scale">${xAxis(axis, 6, label, context?.measureText)}</svg></div><div class="av-axis-rows-viewport"><svg xmlns="http://www.w3.org/2000/svg" data-av-axis-layer="rows" width="${labelWidth}" height="${height}" viewBox="0 0 ${labelWidth} ${height}" role="img" aria-label="${e(title)} row identities">${rowLabels}</svg></div><div class="av-plot-scroll" tabindex="0" role="region" aria-label="${e(title)} plot">${scene}</div></div></div>`;
}
export type LayoutKind = "paired" | "interval" | "distribution" | "trajectory" | "scatter" | "freshness" | "lineage";
/** Retain the original layout input separately from its visual projection. */
export function layoutRecipe(markup: string, kind: LayoutKind, input: Meta): string {
  const context = input.context ? { ...input.context, measureText: undefined } : undefined;
  const value = { ...input, context };
  const json = exactJson(value);
  return markup.replace('data-av-frame="', `data-av-layout-kind="${kind}" data-av-layout-input="${e(json)}" data-av-frame="`);
}
export function statusWord(value?: Status): string { return value === undefined ? "" : value.replace(/-/g, " "); }
