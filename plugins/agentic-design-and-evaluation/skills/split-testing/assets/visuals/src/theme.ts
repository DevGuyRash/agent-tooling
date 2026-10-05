/** Design tokens for both themes. build.mjs compiles this pure module and
 * writes themeCss() ahead of the component styles; nothing here touches a DOM. */

type Palette = Record<string, string>;

const light: Palette = {
  "bg": "#f3f0e8", "surface": "#faf8f2", "raised": "#ffffff", "sunken": "#ece8de",
  "ink": "#17171c", "ink-2": "#44454f", "ink-3": "#5f606b", "line": "#e2dccd", "line-strong": "#c4bba7",
  "accent": "#2944c9", "accent-soft": "#e3e7fb", "accent-ink": "#ffffff", "focus": "#2944c9",
  "pass": "#13795b", "pass-soft": "#d9eee4", "fail": "#c23b1f", "fail-soft": "#f7e0d8",
  "invalid": "#8a8474", "invalid-soft": "#e9e5da", "warn": "#9a6400", "warn-soft": "#f5e7c6",
  "shadow": "0 1px 0 rgba(23,23,28,.04), 0 8px 24px -12px rgba(23,23,28,.18)",
  "grain": "rgba(23,23,28,.045)",
};

const dark: Palette = {
  "bg": "#0c0d11", "surface": "#13151b", "raised": "#1a1d25", "sunken": "#0f1015",
  "ink": "#eceae4", "ink-2": "#b8b7b0", "ink-3": "#87878f", "line": "#252833", "line-strong": "#3a3e4c",
  "accent": "#8fa2ff", "accent-soft": "#1e2440", "accent-ink": "#0c0d11", "focus": "#a9b8ff",
  "pass": "#4cc492", "pass-soft": "#123227", "fail": "#ff7d5e", "fail-soft": "#3a1d16",
  "invalid": "#8e8b83", "invalid-soft": "#24242a", "warn": "#efb453", "warn-soft": "#3a2c12",
  "shadow": "0 1px 0 rgba(0,0,0,.4), 0 10px 30px -12px rgba(0,0,0,.7)",
  "grain": "rgba(255,255,255,.035)",
};

/** Arm identities: a tuned Okabe–Ito order, each paired with a shape so no
 * distinction depends on color alone. Ink-weight variants keep text legible. */
export const armHues = {
  light: ["#1f6fc1", "#d97f00", "#b8508f", "#0f8f78", "#d1501a", "#6a55c9", "#8d7a00", "#4b4e5c"],
  dark: ["#5aa9ff", "#ffad33", "#f07fc0", "#3ccfb0", "#ff8a4f", "#a593ff", "#d6c04a", "#a5a8b8"],
};

const fonts = {
  "font-display": '"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Charter, "Bitstream Charter", "Source Serif Pro", Georgia, serif',
  "font-text": 'Inter, "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif',
  "font-mono": '"JetBrains Mono", "SF Mono", "Cascadia Mono", ui-monospace, Menlo, Consolas, "Liberation Mono", monospace',
};

function block(p: Palette, hues: string[]): string {
  const lines = Object.entries(p).map(([k, v]) => `--av-${k}:${v};`);
  hues.forEach((h, i) => lines.push(`--av-arm-${i}:${h};`));
  // Aliases the bundled Mermaid renderer reads for its palette.
  lines.push("--av-plot:var(--av-raised);", "--av-sheet:var(--av-surface);", "--av-axis:var(--av-ink-3);",
    "--av-subtle:var(--av-sunken);", "--av-inspector-surface:var(--av-accent-soft);");
  return lines.join("");
}

export function themeCss(): string {
  const shared = Object.entries(fonts).map(([k, v]) => `--av-${k}:${v};`).join("")
    + "--av-radius:10px;--av-radius-sm:6px;--av-measure:68ch;--av-page:1180px;--av-gutter:clamp(16px,4vw,40px);";
  return [
    "/* Generated from src/theme.ts by build.mjs. */",
    `:root{${shared}${block(light, armHues.light)}color-scheme:light;}`,
    `:root[data-theme="dark"]{${block(dark, armHues.dark)}color-scheme:dark;}`,
    `@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){${block(dark, armHues.dark)}color-scheme:dark;}}`,
    "",
  ].join("\n");
}

/** Token names both themes define; tests compare the two sets. */
export function themeTokens(): { light: string[]; dark: string[] } {
  return { light: Object.keys(light), dark: Object.keys(dark) };
}

/** Palette values for contrast checks in tests. */
export function themePalettes(): { light: Palette; dark: Palette } {
  return { light: { ...light }, dark: { ...dark } };
}
