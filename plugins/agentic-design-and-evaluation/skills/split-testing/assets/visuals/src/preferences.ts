import { card, documentId, escapeText as e } from "./core";
import { Meta } from "./model";
import { createOwnedStore, OwnedStore } from "./reader-storage";
import { CanvasChoice, backgroundColorKeys, colorKeys, customColorKeys, resolveTheme, IntensityChoice, PaletteChoice, SectionChoice, SpacingChoice, supportedThemePrimitives, TextureChoice, ThemeChoice, ThemeColors, themeChoices, themeColorProperties, themeColorPropertyNames, themeDefaults, themePresets } from "./theme";
export type { CanvasChoice, IntensityChoice, PaletteChoice, SectionChoice, SpacingChoice, TextureChoice, ThemeChoice, ThemeColors } from "./theme";

export interface DisplayPreferences { customColors?: ThemeColors; theme?: ThemeChoice; spacing?: SpacingChoice; sections?: SectionChoice; palette?: PaletteChoice; canvas?: CanvasChoice; texture?: TextureChoice; intensity?: IntensityChoice }
export interface SurfaceInput extends DisplayPreferences {
  id: string;
  /** Trusted composition produced by the report author. */
  body: string;
  /** Opt-in browser storage key; only these display preferences are retained. */
  storageKey?: string;
}
const choices = themeChoices;
type Preferences = Required<Omit<DisplayPreferences, "customColors">>;
const defaults: Preferences = { ...themeDefaults };

function colors(value: unknown): ThemeColors | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const object = value as Record<string, unknown>;
  return colorKeys.every(key => typeof object[key] === "string" && /^#[0-9a-f]{6}$/i.test(object[key] as string)) && backgroundColorKeys.every(key => object[key] === undefined || typeof object[key] === "string" && /^#[0-9a-f]{6}$/i.test(object[key] as string)) ? Object.fromEntries(customColorKeys.filter(key => object[key] !== undefined).map(key => [key, (object[key] as string).toLowerCase()])) as unknown as ThemeColors : null;
}
function declaredColors(value: ThemeColors | undefined): ThemeColors | null {
  const parsed = colors(value);
  if (value !== undefined && !parsed) throw new TypeError("Custom colors need main, secondary and tertiary six-digit hex colors, such as #6750e8.");
  return parsed;
}
function colorAttributes(input: DisplayPreferences): string {
  const value = declaredColors(input.customColors);
  if (!value) return "";
  const style = input.palette === "custom" || input.palette === undefined ? ' style="' + e(Object.entries(themeColorProperties(value)).map(([key, color]) => key + ':' + color).join(';')) + '"' : "";
  return ' data-av-custom-colors="' + e(JSON.stringify(value)) + '"' + style;
}
function preferences(input: DisplayPreferences): Preferences {
  const result = { ...defaults, ...input, palette: input.palette === undefined ? (input.customColors ? "custom" : defaults.palette) : input.palette };
  for (const key of Object.keys(defaults) as (keyof Preferences)[]) {
    if (input[key] === undefined && key !== "palette") result[key] = defaults[key] as never;
    if (!(choices[key] as readonly string[]).includes(result[key])) throw new TypeError("Unknown " + key + ". Use " + choices[key].join(", ") + ".");
  }
  return result;
}
export function surfaceAttributes(input: DisplayPreferences & { storageKey?: string }): string {
  const value = preferences(input);
  if (input.storageKey !== undefined && (typeof input.storageKey !== "string" || !input.storageKey.trim())) throw new TypeError("Supply a nonempty preference storage key or omit it.");
  return 'data-av-preferences ' + (Object.keys(defaults) as (keyof Preferences)[]).map(key => 'data-av-' + key + '="' + value[key] + '"').join(" ") + colorAttributes(input) + (input.storageKey ? ' data-av-storage-key="' + e(input.storageKey) + '"' : "");
}
/** A scope for arbitrary fragments; it imposes no navigation or report layout. */
export function reportSurface(input: SurfaceInput): string {
  if (typeof input.body !== "string") throw new TypeError("A surface body must be trusted author-owned HTML.");
  return '<div class="av-surface" id="' + e(documentId(input.id)) + '" ' + surfaceAttributes(input) + '>' + input.body + '</div>';
}
/** Independent native sections. The body is trusted author-owned composition. */
export function reportSection(input: Omit<Meta, "collapsible"> & { body: string }): string {
  if (typeof input.body !== "string") throw new TypeError("A section body must be trusted author-owned HTML.");
  return card({ ...input, collapsible: true }, input.body);
}
/** Explicit peer boundaries; an omitted mode follows the surrounding preferences. */
export function sectionGroup(input: { body: string; mode?: SectionChoice }): string {
  if (typeof input.body !== "string") throw new TypeError("A section group body must be trusted author-owned HTML.");
  if (input.mode !== undefined && !(choices.sections as readonly string[]).includes(input.mode)) throw new TypeError("Unknown section mode. Use multiple or solo.");
  return '<div class="av-section-group" data-av-section-group' + (input.mode ? ' data-av-section-mode="' + input.mode + '"' : "") + '>' + input.body + '</div>';
}
/** Put this panel anywhere inside its surface. IDs keep native radio groups distinct. */
export function appearanceSettings(input: { id: string }): string {
  const prefix = documentId(input.id), value = defaults;
  const field = (key: keyof Preferences, legend: string, labels: string[]) => '<fieldset class="av-setting"><legend>' + legend + '</legend><div class="av-segmented">' + choices[key].map((choice, i) => '<label><input type="radio" name="' + e(prefix + '-' + key) + '" value="' + choice + '" data-av-setting="' + key + '"' + (value[key] === choice ? " checked" : "") + '><span>' + labels[i] + '</span></label>').join("") + '</div></fieldset>';
  const paletteField = '<fieldset class="av-setting"><legend>Color palette</legend><div class="av-palette-choices">' + [...themePresets, { id: "custom", label: "Custom" }].map(choice => '<label data-av-palette="' + choice.id + '"><input type="radio" name="' + e(prefix + '-palette') + '" value="' + choice.id + '" data-av-setting="palette"' + (value.palette === choice.id ? ' checked' : '') + '><span><i class="av-palette-swatch" aria-hidden="true"><i></i><i></i><i></i></i>' + choice.label + '</span></label>').join('') + '</div></fieldset>';
  const customField = '<fieldset class="av-setting av-custom-colors" data-av-custom-editor hidden><legend>Your colors</legend>' + colorKeys.map((key, index) => '<label><input type="color" data-av-color="' + key + '"><span>' + ['Main', 'Secondary 1', 'Secondary 2'][index] + '</span></label>').join('') + '</fieldset>';
  const backgroundField = '<fieldset class="av-setting av-custom-colors av-background-colors" data-av-custom-editor hidden><legend>Canvas colors</legend>' + backgroundColorKeys.map((key, index) => '<label><input type="color" data-av-color="' + key + '"><span>' + ['Light appearance', 'Dark appearance'][index] + '</span></label>').join('') + '</fieldset>';
  return '<details class="av-settings" data-av-settings data-av-script-only hidden><summary><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 5h16M4 12h16M4 19h16"/><circle cx="8" cy="5" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="19" r="2"/></svg><span>Display</span></summary><div class="av-settings-panel">' + field("theme", "Appearance", ["System", "Light", "Dark"]) + paletteField + customField + backgroundField + field("canvas", "Background", ["Ambient", "Plain", "Textured"]) + '<div class="av-texture-options" data-av-texture-options hidden>' + field("texture", "Texture", ["Grain", "Grid"]) + '</div><div data-av-intensity-options>' + field("intensity", "Background intensity", ["Low", "Moderate"]) + '</div>' + field("spacing", "Spacing", ["Comfortable", "Compact"]) + field("sections", "Sections", ["Multiple open", "One at a time"]) + '<div class="av-settings-footer"><button type="button" class="av-button av-button-quiet" data-av-reset-preferences>Reset preferences</button><output class="av-sr-only" data-av-preference-status aria-live="polite"></output><p class="av-note" data-av-preference-persistence role="status" hidden></p></div></div></details>';
}

interface StoredPreferences extends Preferences { customColors?: ThemeColors }
interface Scope { element: HTMLElement; source: HTMLElement; explicit: boolean; changed: boolean; version: number; value: Preferences; initial: Preferences; key: string | null; colors: ThemeColors | null; initialColors: ThemeColors | null; store: OwnedStore<StoredPreferences> | null; persistence: string }
interface Section { element: HTMLElement; scope: Scope; group: Element }
export interface PreferenceController {
  whenReady(): Promise<void>;
  /** Drain reads and writes already queued by this controller. */
  whenIdle(): Promise<void>;
  change(target: Element): boolean;
  click(target: Element): boolean;
  toggle(target: Element): void;
  refresh(anchor?: Element): void;
  reveal(target: Element): void;
  mirror(element: HTMLElement, source: Element): void;
  snapshot(element: HTMLElement, source: Element): void;
  dismiss(target: Element | null, restoreFocus?: boolean): boolean;
  cleanup(): void;
}

/** Internal controller shared by full workspaces and independently enhanced fragments. */
export function attachPreferences(root: HTMLElement, changed?: () => void): PreferenceController {
  const document = root.ownerDocument, window = document.defaultView;
  const undo: (() => void)[] = [], saved = new WeakMap<Element, Set<string>>();
  let disposed = false;
  const pending = new Set<Promise<unknown>>();
  const initialReads: Promise<unknown>[] = [];
  function track(operation: Promise<unknown>): void {
    pending.add(operation);
    void operation.then(() => pending.delete(operation), () => pending.delete(operation));
  }
  const all = <T extends Element = HTMLElement>(selector: string): T[] => [...(root.matches(selector) ? [root as unknown as T] : []), ...Array.from(root.querySelectorAll<T>(selector))];
  function remember(element: Element, name: string): void {
    const attributes = saved.get(element) || new Set<string>();
    if (attributes.has(name)) return;
    attributes.add(name); saved.set(element, attributes);
    const original = element.getAttribute(name);
    undo.push(() => original === null ? element.removeAttribute(name) : element.setAttribute(name, original));
  }
  function write(element: Element, name: string, value: string | null): void {
    remember(element, name);
    if (value === null) element.removeAttribute(name); else element.setAttribute(name, value);
  }
  function accept(value: unknown, initial: Preferences): Preferences {
    const result = { ...initial };
    if (value && typeof value === "object") for (const key of Object.keys(defaults) as (keyof Preferences)[]) {
      const item = (value as Record<string, unknown>)[key];
      if (typeof item === "string" && (choices[key] as readonly string[]).includes(item)) result[key] = item as never;
    }
    return result;
  }
  function effective(element: Element): Preferences {
    const value: Record<string, string> = {};
    for (const key of Object.keys(defaults)) for (let owner: Element | null = element; owner; owner = owner.parentElement) {
      const candidate = owner.getAttribute("data-av-" + key);
      if (candidate !== null) { value[key] = candidate; break; }
    }
    return accept(value, defaults);
  }
  function decodeStored(value: unknown, initial: Preferences = defaults): StoredPreferences {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new TypeError("Saved display choices must be an object.");
    const object = value as Record<string, unknown>, keys = Object.keys(object);
    if (!keys.length || keys.some(key => !Object.prototype.hasOwnProperty.call(defaults, key) && key !== "customColors")) throw new TypeError("These saved records are not display choices.");
    for (const key of keys) {
      if (key === "customColors") { if (!colors(object[key]) || Object.keys(object[key] as object).some(name => !(customColorKeys as readonly string[]).includes(name))) throw new TypeError("Saved custom colors are invalid."); }
      else if (!(choices[key as keyof Preferences] as readonly unknown[]).includes(object[key])) throw new TypeError("Saved display choices are invalid.");
    }
    return { ...accept(object, initial), ...(object.customColors ? { customColors: colors(object.customColors)! } : {}) };
  }
  function primitives(element: Element | null): Record<string, string> {
    if (!element) return {};
    const computed = window?.getComputedStyle?.(element);
    return Object.fromEntries(supportedThemePrimitives.map(name => {
      let value = computed?.getPropertyValue(name).trim() || "";
      // Also makes scoped inline primitives observable in bounded DOM doubles.
      if (!value) for (let ancestor: Element | null = element; ancestor; ancestor = ancestor.parentElement) {
        value = (ancestor as HTMLElement).style?.getPropertyValue(name).trim() || "";
        if (value) break;
      }
      return [name, value];
    }).filter(([, value]) => !!value));
  }
  const roots = all<HTMLElement>("[data-av-preferences]");
  if (!roots.includes(root)) roots.unshift(root);
  const scopes: Scope[] = roots.map(element => {
    const explicit = element.hasAttribute("data-av-preferences") || Object.keys(defaults).some(key => element.hasAttribute("data-av-" + key));
    const source = (explicit ? element : element.parentElement?.closest<HTMLElement>("[data-av-preferences]") || element.parentElement) || element;
    const initial = effective(element);
    const requestedKey = element.getAttribute("data-av-storage-key");
    const conflict = requestedKey && Array.from(document.querySelectorAll("[data-av-notebook-storage-key]")).some(notebook => notebook.getAttribute("data-av-notebook-storage-key") === requestedKey);
    const key = conflict || !element.id ? null : requestedKey;
    let initialColors: ThemeColors | null = null;
    try { initialColors = colors(JSON.parse(source.getAttribute("data-av-custom-colors") || "null")); } catch { /* Ignore malformed optional metadata. */ }
    const store = key ? createOwnedStore<StoredPreferences>(window, key, { kind: "preferences", reportId: element.id, revision: "1" }, raw => decodeStored(JSON.parse(raw), initial)) : null;
    return { element, source, explicit, changed: false, version: 0, initial, value: { ...initial }, key, colors: initialColors, initialColors, store, persistence: conflict ? "Display choices stay in this session because this saving key is used by the notebook." : requestedKey && !element.id ? "Display choices stay in this session because this surface has no stable identity." : "" };
  });
  // A standalone report can theme the document scrollbar. Embedded sibling
  // reports keep their own scroll surfaces and never compete for page ownership.
  const pageScope = document.querySelectorAll(".av-workspace").length === 1
    ? scopes.find(scope => scope.element.matches(".av-workspace") && scope.element.parentElement === document.body) : undefined;
  const pageStyle = document.documentElement?.style;
  const pageProperties = ["scrollbar-color", "scrollbar-width", "color-scheme", "--av-page-scroll-thumb", "--av-page-scroll-track"];
  if (pageScope && pageStyle) {
    const before = pageProperties.map(name => [name, pageStyle.getPropertyValue(name), pageStyle.getPropertyPriority?.(name) || ""]);
    remember(document.documentElement, "data-av-page-scroll");
    undo.push(() => { for (const [name, value, priority] of before) if (value) pageStyle.setProperty(name, value, priority); else pageStyle.removeProperty(name); });
  }
  const originalOwners = new WeakMap<Element, Scope>();
  const frameLineage = new WeakMap<Element, Element[]>();
  const themeOrigins = new WeakMap<Element, { parent: Element | null; local: Record<string, string> }>();
  const scopeOf = (element: Element): Scope => originalOwners.get(element) || scopes.find(scope => scope.element === element.closest("[data-av-preferences]")) || scopes[0];
  // Preserve original surface ownership and section ancestry when inspection
  // moves a live frame away from its initial parent.
  for (const element of all(".av-card,[data-av-figure],[data-av-notebook],[data-av-reset-preferences]")) {
    originalOwners.set(element, scopeOf(element));
    if (element.matches(".av-card,[data-av-figure],[data-av-notebook]")) {
      const inherited = primitives(element.parentElement), actual = primitives(element);
      themeOrigins.set(element, { parent: element.parentElement, local: Object.fromEntries(Object.entries(actual).filter(([name, value]) => value !== inherited[name])) });
      const lineage: Element[] = [];
      for (let ancestor: Element | null = element; ancestor; ancestor = ancestor.parentElement) if (ancestor.matches("details[data-av-section],details[data-av-object]")) lineage.push(ancestor);
      frameLineage.set(element, lineage);
    }
  }
  const colorControls = new Map(all<HTMLInputElement>("input[data-av-color]").map(control => [control, scopeOf(control)]));
  const colorPreviews = new Map(all<HTMLElement>('label[data-av-palette="custom"]').map(preview => [preview, scopeOf(preview)]));
  const colorEditors = new Map(all<HTMLElement>("[data-av-custom-editor]").map(editor => [editor, scopeOf(editor)]));
  const textureEditors = new Map(all<HTMLElement>("[data-av-texture-options]").map(editor => [editor, scopeOf(editor)]));
  const intensityEditors = new Map(all<HTMLElement>("[data-av-intensity-options]").map(editor => [editor, scopeOf(editor)]));
  for (const control of colorControls.keys()) { const original = control.value; undo.push(() => { control.value = original; }); }
  const controls = new Map(all<HTMLInputElement>("input[data-av-setting]").map(control => [control, scopeOf(control)]));
  for (const control of controls.keys()) { const checked = control.checked; undo.push(() => { control.checked = checked; }); }
  const menus = all<HTMLDetailsElement>("[data-av-settings]");
  for (const menu of menus) remember(menu, "open");
  const statuses = new Map(all<HTMLElement>("[data-av-preference-status]").map(element => [element, scopeOf(element)]));
  const persistenceStatuses = new Map(all<HTMLElement>("[data-av-preference-persistence]").map(element => [element, scopeOf(element)]));
  for (const status of [...statuses.keys(), ...persistenceStatuses.keys()]) { const original = Array.from(status.childNodes); undo.push(() => { status.textContent = ""; for (const child of original) status.appendChild(child); }); }
  const fallbackGroup = document.createElement("div");
  const sections: Section[] = all<HTMLElement>("details[data-av-section],details[data-av-object]").map(element => ({
    element, scope: scopeOf(element),
    group: (element.hasAttribute("data-av-object") ? element.closest("[data-av-explorer]") : element.parentElement?.closest("[data-av-section-group],[data-av-panel],[data-av-section],[data-av-object],[data-av-preferences]")) || fallbackGroup,
  }));
  for (const section of sections) remember(section.element, "open");
  const workspaces = new Map(sections.map(section => [section, section.element.closest<HTMLElement>(".av-workspace")]));
  function peerGroup(section: Section): Element {
    const workspace = workspaces.get(section);
    return section.group.hasAttribute("data-av-panel") && workspace?.getAttribute("data-av-reader-mode") === "all" ? workspace : section.group;
  }
  const mirrors = new Map<HTMLElement, { scope: Scope; source: Element }>();
  const mode = (section: Section): SectionChoice => {
    if (section.group.classList.contains("av-comparing")) return "multiple";
    const supplied = section.group.getAttribute("data-av-section-mode");
    return supplied === "solo" || supplied === "multiple" ? supplied : section.scope.value.sections;
  };
  function select(section: Section): void {
    if (section.element.hasAttribute("data-av-inspection-open") || !section.element.hasAttribute("open") || mode(section) !== "solo") return;
    for (const peer of sections) if (peer !== section && !peer.element.hasAttribute("data-av-inspection-open") && peerGroup(peer) === peerGroup(section) && peer.scope === section.scope) write(peer.element, "open", null);
  }
  function normalize(scope: Scope, anchor?: Element): void {
    const active = anchor || document.activeElement;
    const frame = active?.closest(".av-card");
    const lineage = new Set(frame ? frameLineage.get(frame) || [] : []);
    const retained = new Map<Element, Section>();
    // The temporarily expanded frame has its own dialog; its original peers
    // and its nested disclosure groups retain their independent state.
    const open = sections.filter(section => !section.element.hasAttribute("data-av-inspection-open") && section.scope === scope && mode(section) === "solo" && section.element.hasAttribute("open") && !section.element.closest("[hidden]"));
    for (const section of open) if (lineage.has(section.element) || (active && section.element.contains(active))) retained.set(peerGroup(section), section);
    for (const section of open) if (!retained.has(peerGroup(section)) && active?.contains(section.element)) retained.set(peerGroup(section), section);
    for (const section of open) if (!retained.has(peerGroup(section))) retained.set(peerGroup(section), section);
    for (const section of open) if (retained.get(peerGroup(section)) !== section) write(section.element, "open", null);
  }
  function displayedColors(scope: Scope): ThemeColors {
    const style = window?.getComputedStyle?.(scope.source);
    const fallback = scope.value.palette === "custom" && scope.colors ? scope.colors : (themePresets.find(preset => preset.id === scope.value.palette) || themePresets[0]).colors;
    const brand = Object.fromEntries(colorKeys.map(key => {
      const value = style?.getPropertyValue("--av-brand-" + key).trim() || "";
      return [key, /^#[0-9a-f]{6}$/i.test(value) ? value : fallback[key]];
    })) as unknown as ThemeColors;
    return { ...brand, backgroundLight: scope.colors?.backgroundLight || resolveTheme(brand, "light").paper, backgroundDark: scope.colors?.backgroundDark || resolveTheme(brand, "dark").paper };
  }
  function showPersistence(scope: Scope): void {
    for (const [status, owner] of persistenceStatuses) if (owner === scope) {
      status.textContent = scope.persistence;
      write(status, "hidden", scope.persistence ? null : "");
    }
  }
  function paintDestination(element:HTMLElement,scope:Scope,source?:Element,retain=true):void {
    for(const key of Object.keys(defaults) as (keyof Preferences)[]){if(retain)write(element,'data-av-'+key,scope.value[key]);else element.setAttribute('data-av-'+key,scope.value[key]);}
    if(retain)remember(element,'style');
    const custom=scope.value.palette==='custom'?themeColorProperties(scope.colors||displayedColors(scope)):null;
    for(const name of themeColorPropertyNames){if(custom)element.style.setProperty(name,custom[name]);else element.style.removeProperty(name);}
    if(source){const origin=themeOrigins.get(source),local=Object.fromEntries(Object.entries(origin?.local||{}).map(([name,value])=>[name,(source as HTMLElement).style?.getPropertyValue(name).trim()||window?.getComputedStyle?.(source).getPropertyValue(name).trim()||value]));
      const overrides={...primitives(origin?.parent||scope.source),...local};for(const name of supportedThemePrimitives){if(overrides[name])element.style.setProperty(name,overrides[name]);else element.style.removeProperty(name);}}
  }
  const paintKeys = new WeakMap<Scope, string>();
  const colorFrames = new Map<HTMLElement, number>();
  function pauseColorTransitions(element: HTMLElement): void {
    if (!window?.requestAnimationFrame) return;
    const previous = colorFrames.get(element); if (previous !== undefined) window.cancelAnimationFrame(previous);
    write(element, 'data-av-theme-changing', '');
    colorFrames.set(element, window.requestAnimationFrame(() => {
      if (disposed) return;
      colorFrames.set(element, window.requestAnimationFrame(() => { colorFrames.delete(element); if (!disposed) element.removeAttribute('data-av-theme-changing'); }));
    }));
  }
  function apply(scope: Scope, announce = false, anchor?: Element): void {
    const paintKey = JSON.stringify([scope.value, scope.colors]);
    const changedPaint = paintKeys.get(scope) !== paintKey;
    paintKeys.set(scope, paintKey);
    const destinations = [...(scope.explicit || scope.changed ? [scope.element] : []), ...[...mirrors].filter(([, mirror]) => mirror.scope === scope).map(([element]) => element)];
    for (const element of destinations) { if (changedPaint) pauseColorTransitions(element); paintDestination(element, scope, mirrors.get(element)?.source); }
    for (const [control, owner] of controls) if (owner === scope) control.checked = control.value === scope.value[control.getAttribute("data-av-setting") as keyof Preferences];
    const chosen = { ...displayedColors(scope), ...scope.colors };
    if (scope === pageScope && pageStyle) {
      const palette = scope.value.palette === "custom" ? chosen : (themePresets.find(preset => preset.id === scope.value.palette) || themePresets[0]).colors;
      const properties = themeColorProperties(palette), computed = window?.getComputedStyle?.(scope.element);
      pageStyle.setProperty("--av-page-scroll-thumb", computed?.getPropertyValue("--av-scroll-thumb").trim() || properties["--av-tone-scroll-thumb"]);
      pageStyle.setProperty("--av-page-scroll-track", computed?.getPropertyValue("--av-scroll-track").trim() || properties["--av-tone-scroll-track"]);
      pageStyle.setProperty("scrollbar-color", "var(--av-page-scroll-thumb) var(--av-page-scroll-track)"); pageStyle.setProperty("scrollbar-width", "thin");
      pageStyle.setProperty("color-scheme", scope.value.theme === "system" ? "light dark" : scope.value.theme);
      write(document.documentElement, "data-av-page-scroll", "");
    }
    for (const [preview, owner] of colorPreviews) if (owner === scope) {
      remember(preview, "style");
      for (const key of colorKeys) preview.style.setProperty("--av-brand-" + key, chosen[key]);
    }
    for (const [control, owner] of colorControls) if (owner === scope) control.value = chosen[control.getAttribute("data-av-color") as keyof ThemeColors]!;
    for (const [editor, owner] of colorEditors) if (owner === scope) write(editor, "hidden", scope.value.palette === "custom" ? null : "");
    for (const [editor, owner] of textureEditors) if (owner === scope) write(editor, "hidden", scope.value.canvas === "textured" ? null : "");
    for (const [editor, owner] of intensityEditors) if (owner === scope) write(editor, "hidden", scope.value.canvas === "plain" ? "" : null);
    normalize(scope, anchor);
    showPersistence(scope);
    if (changedPaint) changed?.();
    if (announce) {
      for (const [status, owner] of statuses) if (owner === scope) status.textContent = scope.value.palette + " palette, " + scope.value.theme + " appearance, " + scope.value.canvas + " canvas" + (scope.value.canvas === "textured" ? " with " + scope.value.texture : "") + ", " + scope.value.spacing + " spacing, " + (scope.value.sections === "solo" ? "one section at a time." : "multiple sections may stay open.");
    }
  }
  function persist(scope: Scope, delta: Partial<StoredPreferences>, colorDelta?: Partial<ThemeColors>): void {
    const version = ++scope.version;
    if (!scope.store) return;
    const fallbackColors = scope.colors || displayedColors(scope);
    track(scope.store.update(current => {
      const base = current === null ? { ...scope.initial, ...(scope.initialColors ? { customColors: scope.initialColors } : {}) } : decodeStored(current, scope.initial);
      const next = { ...base, ...delta };
      if (colorDelta) next.customColors = { ...(base.customColors || fallbackColors), ...colorDelta };
      if (!next.customColors) delete next.customColors;
      return next;
    }).then(result => {
      if (disposed || scope.version !== version) return;
      if (result.status === "saved" || result.status === "ready") {
        scope.persistence = "";
        if (result.value) {
          try { const value = decodeStored(result.value, scope.initial); scope.value = accept(value, scope.initial); scope.colors = value.customColors || null; apply(scope); }
          catch { scope.persistence = "The saved display choices could not be read. Your current choices remain in this session."; }
        }
      } else scope.persistence = result.status === "blocked" ? "Display choices remain in this session. Existing saved records are protected because this key has a different owner or format." : "Display choices remain in this session; browser saving is unavailable.";
      showPersistence(scope);
    }));
  }
  for (const scope of scopes) {
    apply(scope);
    if (scope.store) { const reading = scope.store.read().then(result => {
      if (disposed || scope.version !== 0) return;
      if (result.value) {
        try { const stored = decodeStored(result.value, scope.initial); scope.value = accept(stored, scope.initial); scope.colors = stored.customColors || scope.initialColors; }
        catch { scope.persistence = "Saved display choices have an unsupported format. Your current choices remain in this session."; }
      }
      if (result.status === "blocked") scope.persistence = "Display choices remain in this session. Existing saved records are protected because this key has a different owner or format.";
      if (result.status === "unavailable") scope.persistence = "Display choices remain in this session; browser saving is unavailable.";
      apply(scope);
    }); initialReads.push(reading); track(reading); }
  }
  return {
    async whenReady() { await Promise.all(initialReads); },
    async whenIdle() { while (pending.size) await Promise.all([...pending]); },
    change(target) {
      const colorOwner = colorControls.get(target as HTMLInputElement);
      if (colorOwner) {
        const key = target.getAttribute("data-av-color") as keyof ThemeColors, value = (target as HTMLInputElement).value;
        const next = colors({ ...(colorOwner.colors || displayedColors(colorOwner)), [key]: value });
        if (next) { colorOwner.colors = next; colorOwner.value.palette = "custom"; colorOwner.changed = true; apply(colorOwner, true, target); persist(colorOwner, { palette: "custom" }, { [key]: value }); }
        return true;
      }
      const scope = controls.get(target as HTMLInputElement), key = target.getAttribute("data-av-setting") as keyof Preferences;
      if (!scope || !Object.prototype.hasOwnProperty.call(choices, key)) return false;
      const control = target as HTMLInputElement;
      if (control.checked && (choices[key] as readonly string[]).includes(control.value)) {
        const seedCustom = key === "palette" && control.value === "custom" && !scope.colors;
        if (seedCustom) scope.colors = displayedColors(scope);
        scope.value = { ...scope.value, [key]: control.value }; scope.changed = true;
        apply(scope, true, control);
        persist(scope, { [key]: control.value, ...(seedCustom && scope.colors ? { customColors: scope.colors } : {}) });
      }
      return true;
    },
    click(target) {
      const control = target.closest("[data-av-reset-preferences]");
      if (!control) return false;
      const scope = scopeOf(control); scope.value = { ...scope.initial }; scope.colors = scope.initialColors; scope.changed = true; apply(scope, true, control); persist(scope, { ...scope.initial, customColors: scope.initialColors || undefined }); return true;
    },
    refresh(anchor) { for (const scope of scopes) normalize(scope, anchor); },
    toggle(target) { const section = sections.find(section => section.element === target); if (section) select(section); },
    reveal(target) {
      for (let ancestor: Element | null = target; ancestor; ancestor = ancestor.parentElement) {
        const section = sections.find(section => section.element === ancestor);
        if (section) { write(section.element, "open", ""); select(section); }
      }
    },
    snapshot(element,source){const scope=sections.find(section=>section.element===source)?.scope||scopeOf(source);if(!scope.explicit&&!scope.changed)scope.value=effective(scope.source);paintDestination(element,scope,source,false);},
    mirror(element, source) {
      const scope = sections.find(section => section.element === source)?.scope || scopeOf(source);
      if (!scope.explicit && !scope.changed) scope.value = effective(scope.source);
      mirrors.set(element, { scope, source }); apply(scope);
    },
    dismiss(target, restoreFocus = false) {
      let closed = false;
      for (const menu of menus) if (menu.open && (restoreFocus ? !!target && menu.contains(target) : !target || !menu.contains(target))) {
        write(menu, "open", null); if (restoreFocus) menu.querySelector<HTMLElement>("summary")?.focus(); closed = true;
      }
      return closed;
    },
    cleanup() { disposed = true; for (const frame of colorFrames.values()) window?.cancelAnimationFrame(frame); colorFrames.clear(); for (const scope of scopes) scope.store?.close(); for (const restore of undo.reverse()) restore(); mirrors.clear(); },
  };
}
