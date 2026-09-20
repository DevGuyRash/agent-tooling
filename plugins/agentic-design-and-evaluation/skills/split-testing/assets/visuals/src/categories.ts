/** Identity determines appearance; encounter order and display labels do not. */
export type MarkerShape = "circle" | "square" | "diamond" | "triangle" | "cross" | "hexagon";
export interface CategoryStyle { color: number; shape: MarkerShape; dash: string; code?: string }
export interface CategoryDefinition { id: string; label?: string; style?: Partial<Omit<CategoryStyle, "code">> }
export interface ChartContext {
  categories?: readonly CategoryDefinition[];
  width?: number;
  measureText?: (text: string, fontSize?: number) => number;
}
const shapes: MarkerShape[] = ["circle", "square", "diamond", "triangle", "cross", "hexagon"];
const dashes = ["", "7 4", "2 4", "8 3 2 3"];
function hash(text: string): number { let result = 2166136261; for (const point of text) { result ^= point.codePointAt(0)!; result = Math.imul(result, 16777619); } return result >>> 0; }
interface CategoryIndex { byId: Map<string, { index: number; item: CategoryDefinition }>; shapes: Map<MarkerShape, number> }
const indexes = new WeakMap<readonly CategoryDefinition[], CategoryIndex>();
function indexCategories(items: readonly CategoryDefinition[]): CategoryIndex {
  const existing = indexes.get(items); if (existing) return existing;
  const ordered = [...items].sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const index: CategoryIndex = { byId: new Map(), shapes: new Map() };
  ordered.forEach((item, i) => { const shape = item.style?.shape || shapes[i % shapes.length]; index.byId.set(item.id, { index: i, item }); index.shapes.set(shape, (index.shapes.get(shape) || 0) + 1); });
  return index;
}
export function createChartContext(input: ChartContext = {}): ChartContext {
  const seen = new Set<string>();
  const categories = input.categories?.map(item => {
    if (typeof item.id !== "string" || !item.id || seen.has(item.id)) throw new TypeError("Category IDs must be nonempty and unique within a chart context.");
    seen.add(item.id); categoryStyle(item.id, { categories: [item] });
    return Object.freeze({ ...item, ...(item.style ? { style: Object.freeze({ ...item.style }) } : {}) });
  });
  if (input.width !== undefined && (!Number.isFinite(input.width) || input.width < 240)) throw new TypeError("Chart width must be at least 240 CSS pixels.");
  if (input.measureText !== undefined && typeof input.measureText !== "function") throw new TypeError("Chart text measurement must be a function.");
  if (categories) { Object.freeze(categories); indexes.set(categories, indexCategories(categories)); }
  return Object.freeze({ ...input, ...(categories ? { categories } : {}) });
}
export function categoryStyle(id: string, context?: ChartContext): CategoryStyle {
  const value = hash(id), definitions = context?.categories ? indexCategories(context.categories) : null;
  const found = definitions?.byId.get(id), index = found?.index ?? -1, override = found?.item.style;
  const style: CategoryStyle = { color: value % 6 + 1, shape: shapes[index >= 0 ? index % shapes.length : Math.floor(value / 6) % shapes.length], dash: dashes[index >= 0 ? Math.floor(index / 6) % dashes.length : Math.floor(value / 36) % dashes.length], ...(override?.color !== undefined ? { color: override.color } : {}), ...(override?.shape !== undefined ? { shape: override.shape } : {}), ...(override?.dash !== undefined ? { dash: override.dash } : {}) };
  const sameShape = (definitions?.shapes.get(style.shape) || 0) > 1;
  if (index >= 0 && sameShape) { let n = index + 1, code = ""; while (n) { n--; code = String.fromCharCode(65 + n % 26) + code; n = Math.floor(n / 26); } style.code = code; }
  if (!Number.isInteger(style.color) || style.color < 1 || style.color > 6 || !shapes.includes(style.shape) || !/^(?:\d+(?:\.\d+)?(?: +\d+(?:\.\d+)?)*)?$/.test(style.dash)) throw new TypeError("Category styles need color 1–6, a supported marker shape and a numeric dash pattern.");
  return style;
}
export function occurrenceIds(items: { id?: string }[], family: string): string[] {
  const explicit = new Set<string>();
  for (const item of items) if (item.id !== undefined) { if (typeof item.id !== "string" || !item.id || explicit.has(item.id)) throw new TypeError(`${family} IDs must be nonempty and unique.`); explicit.add(item.id); }
  const used = new Set(explicit);
  return items.map((item, index) => {
    if (item.id !== undefined) return item.id;
    let id = `${family} ${index + 1}`; while (used.has(id)) id = "Occurrence " + id;
    used.add(id); return id;
  });
}

export function chartCategories(items: readonly CategoryDefinition[], context?: ChartContext): ChartContext {
  const declared = new Map((context?.categories || []).map(item => [item.id, item]));
  for (const item of items) if (!declared.has(item.id)) declared.set(item.id, item);
  return createChartContext({ ...context, categories: [...declared.values()] });
}
