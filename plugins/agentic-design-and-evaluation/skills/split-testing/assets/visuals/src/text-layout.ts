/** Shared text geometry. This module has no markup, data interpretation, or core dependency. */
export type TextMeasure = (text: string, fontSize?: number) => number;
export interface TextLayout {
  /** Original text, including authored whitespace and hard line breaks. */
  text: string;
  lines: string[];
  lineWidths: number[];
  breakAfter: ("soft" | "hard" | "end")[];
  width: number;
  height: number;
  fontSize: number;
  lineHeight: number;
}
export interface TextLayoutOptions { maxWidth: number; fontSize?: number; lineHeight?: number; measure?: TextMeasure }
export interface Bounds { x: number; y: number; width: number; height: number }

function positive(value: number, label: string): number {
  if (!Number.isFinite(value) || value <= 0) throw new TypeError(`${label} must be a positive finite number.`);
  return value;
}

/** Older hosts keep the whole string indivisible rather than guessing Unicode boundaries. */
export function graphemes(text: string): string[] {
  if (typeof text !== "string") throw new TypeError("Text layout requires a string.");
  type Segmenter = { segment(value: string): Iterable<{ segment: string }> };
  const Constructor = (Intl as unknown as { Segmenter?: new (locale?: string, options?: { granularity: string }) => Segmenter }).Segmenter;
  return Constructor ? Array.from(new Constructor(undefined, { granularity: "grapheme" }).segment(text), part => part.segment) : text ? [text] : [];
}

/** Conservative advance estimate for the bundled sans fonts; native metrics can refine it. */
export function estimateTextWidth(text: string, fontSize = 14): number {
  positive(fontSize, "Font size");
  if (typeof text !== "string") throw new TypeError("Text layout requires a string.");
  let width = 0;
  for (const character of text) {
    if (/[\p{Mark}\u200d\ufe0e\ufe0f]/u.test(character)) continue;
    width += fontSize * (character === "\t" ? 4 : character === " " ? .5 : /[MW@%]/u.test(character) ? 1.15 : 1);
  }
  return width;
}

/** Wrap without dropping characters. An indivisible cluster may exceed maxWidth; width reports it. */
export function wrapText(text: string, options: TextLayoutOptions): TextLayout {
  if (typeof text !== "string") throw new TypeError("Text layout requires a string.");
  const maxWidth = positive(options.maxWidth, "Text width"), fontSize = positive(options.fontSize ?? 14, "Font size");
  const lineHeight = positive(options.lineHeight ?? Math.ceil(fontSize * 1.5), "Line height");
  if (lineHeight < fontSize) throw new TypeError("Line height must be at least the font size.");
  const measure = options.measure ?? (value => estimateTextWidth(value, fontSize));
  const measured = (value: string): number => {
    const width = measure(value, fontSize);
    if (!Number.isFinite(width) || width < 0) throw new TypeError("Text measurement must return a nonnegative finite width.");
    return width;
  };
  const lines: string[] = [], lineWidths: number[] = [], breakAfter: TextLayout["breakAfter"] = [];
  const append = (value: string, after: "soft" | "hard" | "end") => { lines.push(value); lineWidths.push(measured(value)); breakAfter.push(after); };
  const paragraphs = text.split(/\r\n|\r|\n/);
  paragraphs.forEach((paragraph, index) => {
    let current: string[] = [];
    for (const cluster of graphemes(paragraph)) {
      current.push(cluster);
      while (current.length > 1 && measured(current.join("")) > maxWidth) {
        let cut = current.length - 1;
        // Prefer a word boundary; long identifiers and CJK text can still wrap between clusters.
        for (let i = current.length - 2; i >= 0; i--) if (/[\s\-/]$/u.test(current[i])) { cut = i + 1; break; }
        append(current.slice(0, cut).join(""), "soft"); current = current.slice(cut);
      }
    }
    append(current.join(""), index === paragraphs.length - 1 ? "end" : "hard");
  });
  return { text, lines, lineWidths, breakAfter, width: lineWidths.reduce((maximum, width) => Math.max(maximum, width), 0), height: lines.length * lineHeight, fontSize, lineHeight };
}

/** y denotes the top of the text block, not its first baseline. */
export function textBounds(layout: TextLayout, position: { x: number; y: number; anchor?: "start" | "middle" | "end" }): Bounds {
  const offset = position.anchor === "middle" ? layout.width / 2 : position.anchor === "end" ? layout.width : 0;
  return { x: position.x - offset, y: position.y, width: layout.width, height: layout.height };
}

export function unionBounds(rectangles: Bounds[], padding = 0): Bounds {
  if (!Number.isFinite(padding) || padding < 0) throw new TypeError("Bounds padding must be a nonnegative finite number.");
  if (!rectangles.length) return { x: -padding, y: -padding, width: padding * 2, height: padding * 2 };
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  for (const rect of rectangles) {
    if (![rect.x, rect.y, rect.width, rect.height].every(Number.isFinite) || rect.width < 0 || rect.height < 0) throw new TypeError("Text bounds must contain finite coordinates and nonnegative dimensions.");
    left = Math.min(left, rect.x); top = Math.min(top, rect.y); right = Math.max(right, rect.x + rect.width); bottom = Math.max(bottom, rect.y + rect.height);
  }
  return { x: left - padding, y: top - padding, width: right - left + padding * 2, height: bottom - top + padding * 2 };
}

/** Opt-in native metric adapter. Call again after the intended fonts become available. */
export function browserTextMeasure(document: Document, font: string): TextMeasure | null {
  try {
    const context = document.createElement("canvas").getContext("2d");
    if (!context) return null;
    context.font = font;
    const baseFont = context.font || font;
    return (text, fontSize) => {
      const requested = fontSize === undefined ? baseFont : baseFont.replace(/(^|\s)(?:\d*\.?\d+)(?:px|pt|pc|em|rem|%)(?=\s|\/|$)/, (_, prefix: string) => `${prefix}${positive(fontSize, "Font size")}px`);
      if (context.font !== requested) context.font = requested;
      const metric = context.measureText(text);
      const ink = metric.actualBoundingBoxLeft + metric.actualBoundingBoxRight;
      return Math.max(metric.width, Number.isFinite(ink) ? ink : 0);
    };
  } catch { return null; }
}
