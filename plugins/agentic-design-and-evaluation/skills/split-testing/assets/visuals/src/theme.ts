/** Pure theme definitions shared by authoring, controls and generated CSS. */
export interface ThemeColors { main: string; secondary: string; tertiary: string; backgroundLight?: string; backgroundDark?: string }
export const themePresets = [
  { id: "indigo", label: "Indigo", colors: { main: "#6750e8", secondary: "#008596", tertiary: "#de587f" } },
  { id: "ocean", label: "Ocean", colors: { main: "#0089ae", secondary: "#7762da", tertiary: "#dc724b" } },
  { id: "graphite", label: "Graphite", colors: { main: "#566078", secondary: "#397bce", tertiary: "#c15c87" } },
  { id: "aurora", label: "Aurora", colors: { main: "#8862e6", secondary: "#009e9a", tertiary: "#e06491" } },
  { id: "citrus", label: "Citrus", colors: { main: "#c59a26", secondary: "#248978", tertiary: "#7165cc" } },
  { id: "rose", label: "Rose", colors: { main: "#d65a84", secondary: "#5d76d3", tertiary: "#219683" } },
] as const;
export type PaletteChoice = typeof themePresets[number]["id"] | "custom";
export type ThemeChoice = "system" | "light" | "dark";
export type CanvasChoice = "ambient" | "plain" | "textured";
export type TextureChoice = "grain" | "grid";
export type IntensityChoice = "low" | "moderate";
export type SpacingChoice = "comfortable" | "compact";
export type SectionChoice = "multiple" | "solo";
export const themeChoices = {
  palette: [...themePresets.map(preset => preset.id), "custom"] as readonly PaletteChoice[],
  canvas: ["ambient", "plain", "textured"] as const,
  texture: ["grain", "grid"] as const,
  intensity: ["low", "moderate"] as const,
  theme: ["system", "light", "dark"] as const,
  spacing: ["comfortable", "compact"] as const,
  sections: ["multiple", "solo"] as const,
};
export const themeDefaults = { theme: "system", spacing: "comfortable", sections: "multiple", palette: "indigo", canvas: "ambient", texture: "grain", intensity: "low" } as const;
export const colorKeys = ["main", "secondary", "tertiary"] as const;
export const backgroundColorKeys = ["backgroundLight", "backgroundDark"] as const;
export const customColorKeys = [...colorKeys, ...backgroundColorKeys] as const;

type Color = readonly [number, number, number];
type Mode = "light" | "dark";
const rgb = (hex: string): Color => [1, 3, 5].map(start => parseInt(hex.slice(start, start + 2), 16)) as unknown as Color;
const hex = (color: Color): string => "#" + color.map(channel => Math.round(channel).toString(16).padStart(2, "0")).join("");
const mix = (first: string, second: string, ratio: number): string => hex(rgb(first).map((channel, index) => channel * ratio + rgb(second)[index] * (1 - ratio)) as unknown as Color);
function luminance(value: string): number {
  const channels = rgb(value).map(channel => { const value = channel / 255; return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4; });
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
}
function contrast(first: string, second: string): number {
  const a = luminance(first), b = luminance(second);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}
/** Retain as much of the supplied hue as possible against the actual theme surfaces. */
function readable(brand: string, backgrounds: string[], mode: Mode, minimum = 4.8): string {
  const preferred = mode === "light" ? "#101521" : "#ffffff";
  const destination = [preferred, "#000000", "#ffffff"].sort((a, b) => Math.min(...backgrounds.map(background => contrast(b, background))) - Math.min(...backgrounds.map(background => contrast(a, background))))[0];
  for (let percent = 100; percent >= 0; percent--) {
    const result = mix(brand, destination, percent / 100);
    if (backgrounds.every(background => contrast(result, background) >= minimum)) return result;
  }
  return destination;
}

interface SurfaceRole { color: typeof colorKeys[number]; light: readonly [string, number]; dark: readonly [string, number] }
/** Role names are also the supported --av-palette-* author override interface. */
export const themeSurfaceRoles: Record<string, SurfaceRole> = {
  paper: { color: "main", light: ["#f8fafc", .018], dark: ["#101722", .045] },
  sheet: { color: "main", light: ["#ffffff", .008], dark: ["#18202c", .035] },
  white: { color: "tertiary", light: ["#ffffff", .012], dark: ["#202a37", .035] },
  subtle: { color: "secondary", light: ["#f4f7fa", .08], dark: ["#202b39", .09] },
  hover: { color: "secondary", light: ["#f4f7fa", .14], dark: ["#263140", .12] },
  "header-surface": { color: "main", light: ["#ffffff", .025], dark: ["#1b2432", .06] },
  "tool-surface": { color: "secondary", light: ["#f5f9fc", .05], dark: ["#1b2938", .065] },
  "inspector-surface": { color: "tertiary", light: ["#fcf9fc", .04], dark: ["#252536", .06] },
  "node-surface": { color: "tertiary", light: ["#ffffff", .055], dark: ["#273142", .10] },
  plot: { color: "main", light: ["#ffffff", .012], dark: ["#151d29", .035] },
  "accent-pale": { color: "main", light: ["#ffffff", .12], dark: ["#182331", .15] },
  selection: { color: "secondary", light: ["#ffffff", .19], dark: ["#1a2938", .18] },
  "heat-low": { color: "main", light: ["#ffffff", .025], dark: ["#ffffff", .025] },
  "heat-high": { color: "main", light: ["#ffffff", .34], dark: ["#ffffff", .34] },
};
export const themeFixedRoles: Record<string, readonly [string, string]> = {
  sage: ["#246457", "#70d6b5"], "sage-pale": ["#eaf6ef", "#193d36"],
  brass: ["#77570c", "#f5cf80"], "brass-pale": ["#fff6df", "#40331b"],
  mineral: ["#2853a1", "#a2c2ff"], "mineral-pale": ["#edf3ff", "#203651"],
  failure: ["#933934", "#ffb3a7"], "failure-pale": ["#fff0ec", "#422a2e"],
  uncertain: ["#65488b", "#d1b9f5"], "uncertain-pale": ["#f3eefb", "#352b4c"],
  "image-paper": ["#ffffff", "#ffffff"],
  "series-4": ["#196aa1", "#8ccaff"], "series-5": ["#8b356a", "#f2acda"], "series-6": ["#57651b", "#d1df8c"],
};
const foregroundRoles = ["ink", "muted", "faint", "accent", "secondary", "tertiary", "heading", "subheading", "tool-ink", "inspector-ink", "axis", "line", "line-strong", "focus", "selection-ink", "heat-ink", "series-1", "series-2", "series-3", "scroll-thumb", "scroll-track", "canvas-main", "canvas-secondary", "canvas-tertiary"];
export const themeRoles = [...Object.keys(themeSurfaceRoles), ...foregroundRoles, ...Object.keys(themeFixedRoles)] as readonly string[];
export const supportedThemePrimitives = themeRoles.map(role => "--av-palette-" + role);

export function resolveTheme(colors: ThemeColors, mode: Mode): Record<string, string> {
  const result: Record<string, string> = {};
  const heatBase = readable(colors.main, ["#ffffff"], "light", 3.2);
  const background = mode === "light" ? colors.backgroundLight : colors.backgroundDark;
  const inkMode = background ? (contrast("#000000", background) >= contrast("#ffffff", background) ? "light" : "dark") : mode;
  const canvasTone = (value: string): string => {
    if (!background) return value;
    const foreground = inkMode === "light" ? "#000000" : "#ffffff";
    const available = contrast(foreground, background);
    // Near middle gray, keep every channel on the readable side of the canvas.
    // Elsewhere, retain raised surface colors with room for background decoration.
    if (available < 5.2) return hex(rgb(value).map((channel, index) => inkMode === "light" ? Math.max(channel, rgb(background)[index]) : Math.min(channel, rgb(background)[index])) as unknown as Color);
    for (let percent = 100; percent >= 0; percent--) {
      const candidate = mix(value, background, percent / 100);
      if (contrast(foreground, candidate) >= Math.min(7, available)) return candidate;
    }
    return background;
  };
  for (const [name, role] of Object.entries(themeSurfaceRoles)) {
    const heat = name.startsWith("heat-");
    const base = background && !heat ? mix("#ffffff", background, name === "plot" ? .015 : inkMode === "light" ? .16 : .055) : role[mode][0];
    const tone = mix(heat ? heatBase : colors[role.color], base, role[mode][1]);
    result[name] = name === "paper" && background ? background : background && !heat ? canvasTone(tone) : tone;
  }
  const surfaces = Object.keys(themeSurfaceRoles).filter(name => !name.startsWith("heat-")).map(name => result[name]);
  // Bound the strongest supported canvas decoration, including textured mode.
  for (const key of colorKeys) result["canvas-" + key] = canvasTone(colors[key]);
  const decorated = mix(result["canvas-main"], mix(result["canvas-secondary"], mix(result["canvas-tertiary"], result.paper, .10), .14), .20);
  surfaces.push(decorated);
  if (!background) surfaces.push(mix(mode === "light" ? "#000000" : "#ffffff", decorated, .05));
  result.ink = readable(mix(colors.main, inkMode === "light" ? "#152032" : "#f3f7ff", .12), surfaces, inkMode, 7);
  result.muted = readable(mix(colors.secondary, inkMode === "light" ? "#39485c" : "#c2cddd", .18), surfaces, inkMode);
  result.faint = result.muted;
  result.accent = readable(colors.main, surfaces, inkMode);
  result.secondary = readable(colors.secondary, surfaces, inkMode);
  result.tertiary = readable(colors.tertiary, surfaces, inkMode);
  result.heading = result.ink;
  result.subheading = readable(mix(colors.tertiary, result.ink, .18), surfaces, inkMode, 7);
  result["tool-ink"] = result.secondary;
  result["inspector-ink"] = result.tertiary;
  result.axis = readable(mix(colors.secondary, inkMode === "light" ? "#546275" : "#acbacf", .25), [result.plot], inkMode, 3.2);
  result.line = mix(colors.main, inkMode === "light" ? "#d4dce7" : "#415067", .18);
  result["line-strong"] = readable(mix(colors.main, inkMode === "light" ? "#8190a5" : "#8b9db8", .25), surfaces, inkMode, 3.2);
  result.focus = result.accent;
  result["selection-ink"] = result.ink;
  result["heat-ink"] = readable(colors.main, [result["heat-low"], result["heat-high"]], "light");
  result["series-1"] = result.accent;
  result["series-2"] = result.secondary;
  result["series-3"] = result.tertiary;
  result["scroll-thumb"] = result.secondary;
  result["scroll-track"] = result.paper;
  for (const [name, values] of Object.entries(themeFixedRoles)) result[name] = values[(background ? inkMode : mode) === "light" ? 0 : 1];
  if (background) for (const name of Object.keys(themeFixedRoles)) {
    if (name.startsWith("series-")) result[name] = readable(result[name], [result.plot], inkMode, 3.2);
    else if (result[name + "-pale"]) result[name] = readable(result[name], [...surfaces, result[name + "-pale"]], inkMode);
  }
  return result;
}

// Bounded by color choices rather than report size. Return copies so callers
// cannot corrupt the next surface's theme through a mutated result object.
const propertyCache = new Map<string, Record<string, string>>();
/** Trusted CSS properties derived exclusively from validated hex brand colors. */
export function themeColorProperties(colors: ThemeColors): Record<string, string> {
  if (!colorKeys.every(key => /^#[0-9a-f]{6}$/i.test(colors[key])) || !backgroundColorKeys.every(key => colors[key] === undefined || /^#[0-9a-f]{6}$/i.test(colors[key]!))) throw new TypeError("Theme colors must be six-digit hex colors.");
  const key = JSON.stringify(customColorKeys.map(name => colors[name]?.toLowerCase() || ''));
  const cached = propertyCache.get(key); if (cached) return { ...cached };
  const light = resolveTheme(colors, "light"), dark = resolveTheme(colors, "dark");
  const properties = Object.fromEntries([
    ...colorKeys.map(key => ["--av-brand-" + key, colors[key].toLowerCase()]),
    ...themeRoles.map(role => ["--av-tone-" + role, `light-dark(${light[role]}, ${dark[role]})`]),
  ]);
  if (propertyCache.size >= 32) propertyCache.delete(propertyCache.keys().next().value!);
  propertyCache.set(key, properties); return { ...properties };
}
export const themeColorPropertyNames = [...colorKeys.map(key => "--av-brand-" + key), ...themeRoles.map(role => "--av-tone-" + role)];

const scopes = ".av-report, .av-workspace, .av-card, .av-focus-dialog, .av-surface, .av-settings, .av-toast";
const canvases = ".av-report, .av-workspace, .av-surface, .av-focus-dialog";
function declarations(properties: Record<string, string>): string { return Object.entries(properties).map(([name, value]) => `  ${name}: ${value};`).join("\n"); }
function grain(alpha: number): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180"><filter id="g"><feTurbulence type="fractalNoise" baseFrequency=".84" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="linear" slope="${alpha}"/></feComponentTransfer></filter><path filter="url(#g)" opacity=".65" d="M0 0h180v180H0z"/></svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}
/** Only trusted, pure definitions are executed by the stylesheet builder. */
export function themeCss(): string {
  const presets = themePresets.map((preset, index) => `${index === 0 ? ":root, " : ""}[data-av-palette="${preset.id}"] {\n${declarations(themeColorProperties(preset.colors))}\n}`).join("\n");
  const roles = Object.fromEntries(themeRoles.map(role => ["--av-" + role, `var(--av-palette-${role}, var(--av-tone-${role}))`]));
  return `/* Generated theme definitions from src/theme.ts. Edit that source, not this block. */
${presets}
:where(${scopes}) {
${declarations(roles)}
  --av-shadow: light-dark(#24344a0c, #00000026);
  --av-backdrop: light-dark(#17243873, #050a12b8);
  --av-display: Aptos, "Segoe UI", ui-sans-serif, system-ui, -apple-system, sans-serif;
  --av-sans: Aptos, "Segoe UI", ui-sans-serif, system-ui, -apple-system, sans-serif;
  --av-mono: "SFMono-Regular", Consolas, "Liberation Mono", ui-monospace, monospace;
  --av-radius: 1rem;
  --av-control-radius: .55rem;
  --av-reading-measure: 74ch;
  --av-space-1: .25rem; --av-space-2: .5rem; --av-space-3: .75rem;
  --av-space-4: 1rem; --av-space-6: 1.5rem; --av-space-8: 2rem;
  --av-ease: cubic-bezier(.2, .75, .25, 1);
  color-scheme: var(--av-scheme, light dark);
  color: var(--av-ink);
  font: 16px/1.6 var(--av-sans);
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  overflow-wrap: anywhere;
}
[data-av-theme="light"] { --av-scheme: light; }
[data-av-theme="dark"] { --av-scheme: dark; }
[data-av-theme="system"] { --av-scheme: light dark; }
[data-av-spacing="comfortable"] { --av-frame-space: 1.35rem; --av-cell-y: .85rem; --av-frame-gap: 1.15rem; }
[data-av-spacing="compact"] { --av-frame-space: .85rem; --av-cell-y: .5rem; --av-frame-gap: .75rem; }
:where(${canvases}) {
  --av-wash-main: 5%; --av-wash-secondary: 3%; --av-wash-tertiary: 2%; --av-grid-strength: 9%;
  --av-grain-image: ${grain(.04)};
  --av-ambient-image: radial-gradient(ellipse at 95% 0%, color-mix(in srgb, var(--av-canvas-main) var(--av-wash-main), transparent), transparent 48rem), radial-gradient(ellipse at 0% 25%, color-mix(in srgb, var(--av-canvas-secondary) var(--av-wash-secondary), transparent), transparent 38rem), linear-gradient(135deg, color-mix(in srgb, var(--av-canvas-tertiary) var(--av-wash-tertiary), transparent), transparent 65%);
  --av-grid-image: linear-gradient(color-mix(in srgb, var(--av-secondary) var(--av-grid-strength), transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--av-secondary) var(--av-grid-strength), transparent) 1px, transparent 1px);
  --av-texture-image: var(--av-grain-image); --av-texture-size: 180px 180px;
  --av-canvas-image: var(--av-ambient-image); --av-canvas-size: auto;
}
[data-av-intensity="moderate"] { --av-wash-main: 20%; --av-wash-secondary: 14%; --av-wash-tertiary: 10%; --av-grid-strength: 16%; --av-grain-image: ${grain(.075)}; }
[data-av-texture="grid"] { --av-texture-image: var(--av-grid-image); --av-texture-size: 28px 28px, 28px 28px; }
[data-av-canvas="plain"] { --av-canvas-image: none; --av-canvas-size: auto; }
[data-av-canvas="ambient"] { --av-canvas-image: var(--av-ambient-image); --av-canvas-size: auto; }
[data-av-canvas="textured"] { --av-canvas-image: var(--av-texture-image), var(--av-ambient-image); --av-canvas-size: var(--av-texture-size), auto, auto, auto; }
:is(${canvases}) { background-color: var(--av-paper); background-image: var(--av-canvas-image); background-size: var(--av-canvas-size); }
`;
}
