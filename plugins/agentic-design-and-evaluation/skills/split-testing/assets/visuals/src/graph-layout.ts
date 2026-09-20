import { Bounds, TextLayout, TextMeasure, unionBounds, wrapText } from "./text-layout";

export interface GraphNodeInput { id: string; label: string; kind: string }
export interface GraphEdgeInput { id: string; from: string; to: string; relation: string }
export interface GraphPoint { x: number; y: number }
export interface GraphNodeLayout extends Bounds { index: number; id: string; label: TextLayout; identity: TextLayout; kind: TextLayout }
export interface GraphEdgeLayout {
  index: number; id: string; from: string; to: string; source: number; target: number; lane: number;
  box: Bounds; label: TextLayout; identity: TextLayout; points: GraphPoint[]; arrow: GraphPoint[];
}
export interface GraphLayout { nodes: GraphNodeLayout[]; edges: GraphEdgeLayout[]; width: number; height: number }
type Side = "left" | "right" | "top" | "bottom";
const center = (rect: Bounds): GraphPoint => ({ x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 });
const inflate = (rect: Bounds, space: number): Bounds => ({ x: rect.x - space, y: rect.y - space, width: rect.width + space * 2, height: rect.height + space * 2 });
const intersects = (a: Bounds, b: Bounds, gap = 0): boolean => a.x < b.x + b.width + gap && a.x + a.width + gap > b.x && a.y < b.y + b.height + gap && a.y + a.height + gap > b.y;
const samePoint = (a: GraphPoint, b: GraphPoint): boolean => a.x === b.x && a.y === b.y;

function simplify(points: GraphPoint[]): GraphPoint[] {
  const result: GraphPoint[] = [];
  for (const point of points) {
    if (result.length && samePoint(result[result.length - 1], point)) continue;
    while (result.length > 1) {
      const a = result[result.length - 2], b = result[result.length - 1];
      const collinear = (a.x === b.x && b.x === point.x) || (a.y === b.y && b.y === point.y);
      if (!collinear || (b.x - a.x) * (point.x - b.x) + (b.y - a.y) * (point.y - b.y) < 0) break;
      result.pop();
    }
    result.push(point);
  }
  return result;
}

interface SearchState { key: number; x: number; y: number; direction: number; cost: number; score: number }
class Queue {
  private items: SearchState[] = [];
  get length(): number { return this.items.length; }
  push(value: SearchState): void {
    this.items.push(value); let i = this.items.length - 1;
    while (i > 0) { const parent = (i - 1) >> 1; if (this.items[parent].score <= value.score) break; this.items[i] = this.items[parent]; i = parent; }
    this.items[i] = value;
  }
  pop(): SearchState {
    const first = this.items[0], last = this.items.pop()!;
    if (this.items.length) {
      let i = 0;
      while (i * 2 + 1 < this.items.length) {
        let child = i * 2 + 1;
        if (child + 1 < this.items.length && this.items[child + 1].score < this.items[child].score) child++;
        if (this.items[child].score >= last.score) break;
        this.items[i] = this.items[child]; i = child;
      }
      this.items[i] = last;
    }
    return first;
  }
}

/** Orthogonal visibility-grid search. Obstacles, rather than node order, determine detours. */
function route(start: GraphPoint, finish: GraphPoint, obstacles: Bounds[]): GraphPoint[] {
  if (samePoint(start, finish)) return [start];
  const extent = unionBounds(obstacles, 28);
  const xs = [...new Set([start.x, finish.x, extent.x, extent.x + extent.width, ...obstacles.flatMap(rect => [rect.x, rect.x + rect.width])])].sort((a, b) => a - b);
  const ys = [...new Set([start.y, finish.y, extent.y, extent.y + extent.height, ...obstacles.flatMap(rect => [rect.y, rect.y + rect.height])])].sort((a, b) => a - b);
  // Native font metrics are fractional; equivalent inflated boundaries can differ by an ULP.
  const epsilon = Math.max(1e-7, Math.max(Math.abs(extent.x), Math.abs(extent.y), extent.width, extent.height) * Number.EPSILON * 8);
  const horizontal = new Map<number, [number, number][]>(), vertical = new Map<number, [number, number][]>();
  function clear(a: GraphPoint, b: GraphPoint): boolean {
    const alongX = a.y === b.y, coordinate = alongX ? a.y : a.x, cache = alongX ? horizontal : vertical;
    let blocks = cache.get(coordinate);
    if (!blocks) {
      blocks = [];
      for (const rect of obstacles) {
        if (alongX ? coordinate > rect.y + epsilon && coordinate < rect.y + rect.height - epsilon : coordinate > rect.x + epsilon && coordinate < rect.x + rect.width - epsilon) blocks.push(alongX ? [rect.x, rect.x + rect.width] : [rect.y, rect.y + rect.height]);
      }
      cache.set(coordinate, blocks);
    }
    const low = Math.min(alongX ? a.x : a.y, alongX ? b.x : b.y), high = Math.max(alongX ? a.x : a.y, alongX ? b.x : b.y);
    return !blocks.some(([left, right]) => high > left + epsilon && low < right - epsilon);
  }
  const key = (x: number, y: number, direction: number) => (y * xs.length + x) * 3 + direction;
  const initial: SearchState = { key: key(xs.indexOf(start.x), ys.indexOf(start.y), 0), x: xs.indexOf(start.x), y: ys.indexOf(start.y), direction: 0, cost: 0, score: 0 };
  const costs = new Map<number, number>([[initial.key, 0]]), parents = new Map<number, number>(), states = new Map<number, SearchState>([[initial.key, initial]]), queue = new Queue(); queue.push(initial);
  while (queue.length) {
    const current = queue.pop();
    if (current.cost !== costs.get(current.key)) continue;
    const point = { x: xs[current.x], y: ys[current.y] };
    if (samePoint(point, finish)) {
      const result: GraphPoint[] = []; let cursor: number | undefined = current.key;
      while (cursor !== undefined) { const state = states.get(cursor)!; result.push({ x: xs[state.x], y: ys[state.y] }); cursor = parents.get(cursor); }
      return simplify(result.reverse());
    }
    for (const [dx, dy, direction] of [[1, 0, 1], [0, 1, 2], [-1, 0, 1], [0, -1, 2]]) {
      const x = current.x + dx, y = current.y + dy;
      if (x < 0 || x >= xs.length || y < 0 || y >= ys.length) continue;
      const nextPoint = { x: xs[x], y: ys[y] };
      if (!clear(point, nextPoint)) continue;
      const cost = current.cost + Math.abs(nextPoint.x - point.x) + Math.abs(nextPoint.y - point.y) + (current.direction && current.direction !== direction ? 18 : 0);
      const nextKey = key(x, y, direction);
      if (cost >= (costs.get(nextKey) ?? Infinity)) continue;
      const next = { key: nextKey, x, y, direction, cost, score: cost + Math.abs(finish.x - nextPoint.x) + Math.abs(finish.y - nextPoint.y) };
      costs.set(nextKey, cost); parents.set(nextKey, current.key); states.set(nextKey, next); queue.push(next);
    }
  }
  throw new TypeError("A relationship cannot be routed around the supplied graph boxes. Increase the chart width or use a scoped graph.");
}

function facing(rect: Bounds, point: GraphPoint): Side {
  const c = center(rect), dx = point.x - c.x, dy = point.y - c.y;
  return Math.abs(dx) / rect.width >= Math.abs(dy) / rect.height ? dx >= 0 ? "right" : "left" : dy >= 0 ? "bottom" : "top";
}
function port(rect: Bounds, side: Side, fraction: number): GraphPoint {
  return side === "left" || side === "right" ? { x: rect.x + (side === "right" ? rect.width : 0), y: rect.y + 14 + (rect.height - 28) * fraction }
    : { x: rect.x + 14 + (rect.width - 28) * fraction, y: rect.y + (side === "bottom" ? rect.height : 0) };
}
function stub(point: GraphPoint, side: Side, distance: number): GraphPoint {
  return { x: point.x + (side === "left" ? -distance : side === "right" ? distance : 0), y: point.y + (side === "top" ? -distance : side === "bottom" ? distance : 0) };
}

/** Supplied-order rows are a reading layout, never an inferred hierarchy or weighting. */
export function layoutGraph(nodeInputs: GraphNodeInput[], edgeInputs: GraphEdgeInput[], options: { width?: number; measure?: TextMeasure } = {}): GraphLayout {
  const requested = options.width ?? 1120;
  if (!Number.isFinite(requested) || requested < 240) throw new TypeError("Graph width must be at least 240 CSS pixels.");
  const index = new Map<string, number>();
  nodeInputs.forEach((node, i) => { if (typeof node.id !== "string" || !node.id || index.has(node.id)) throw new TypeError("Graph node IDs must be nonempty and unique."); index.set(node.id, i); });
  const edgeIds = new Set<string>(), pairs = new Map<string, number>();
  const lanes = edgeInputs.map(edge => {
    if (!index.has(edge.from) || !index.has(edge.to)) throw new TypeError("A graph relationship references an undeclared node.");
    if (typeof edge.id !== "string" || !edge.id || edgeIds.has(edge.id)) throw new TypeError("Graph relationship IDs must be nonempty and unique.");
    edgeIds.add(edge.id);
    const pair = JSON.stringify([edge.from, edge.to].sort()), lane = pairs.get(pair) ?? 0; pairs.set(pair, lane + 1); return lane;
  });
  const maxLane = lanes.reduce((maximum, lane) => Math.max(maximum, lane), 0), separation = (12 + maxLane * 6) * 2 + 8;
  const labelWidth = Math.min(260, Math.max(128, requested - 104));
  const labels = edgeInputs.map(edge => {
    const label = wrapText(edge.relation, { maxWidth: labelWidth, fontSize: 14, lineHeight: 20, measure: options.measure });
    const identity = wrapText(edge.id, { maxWidth: labelWidth, fontSize: 12, lineHeight: 18, measure: options.measure });
    return { label, identity, width: Math.max(label.width, identity.width, Math.min(140, labelWidth)) + 24, height: label.height + identity.height + 28 };
  });
  const gap = Math.max(360, labels.reduce((maximum, label) => Math.max(maximum, label.width), 0) + separation * 2);
  const columns = nodeInputs.length > 1 && requested >= 640 + gap + 80 ? 2 : 1;
  const targetWidth = Math.min(360, Math.max(160, (requested - 80 - (columns - 1) * gap) / columns));
  const nodes = nodeInputs.map((node, i): GraphNodeLayout => {
    const label = wrapText(node.label, { maxWidth: targetWidth - 32, fontSize: 14, lineHeight: 20, measure: options.measure });
    const identity = wrapText(node.id, { maxWidth: targetWidth - 32, fontSize: 12, lineHeight: 18, measure: options.measure });
    const kind = wrapText(node.kind, { maxWidth: targetWidth - 32, fontSize: 12, lineHeight: 18, measure: options.measure });
    return { id: node.id, index: i, label, identity, kind, x: 0, y: 0, width: Math.max(targetWidth, label.width + 32, identity.width + 32, kind.width + 32), height: label.height + identity.height + kind.height + 40 };
  });
  const columnWidth = nodes.reduce((maximum, node) => Math.max(maximum, node.width), targetWidth), rowGap = Math.max(160, separation * 2 + 72);
  let rowY = 40;
  for (let i = 0; i < nodes.length; i += columns) {
    let height = 0;
    for (let column = 0; column < columns && i + column < nodes.length; column++) { const node = nodes[i + column]; node.x = 40 + column * (columnWidth + gap); node.y = rowY; height = Math.max(height, node.height); }
    rowY += height + rowGap;
  }
  const occupied: Bounds[] = [...nodes];
  const edges = edgeInputs.map((edge, i): GraphEdgeLayout => {
    const source = index.get(edge.from)!, target = index.get(edge.to)!, a = center(nodes[source]), b = center(nodes[target]), metrics = labels[i];
    const desired = source === target ? { x: nodes[source].x + nodes[source].width + gap / 2, y: a.y } : { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    let box: Bounds | undefined;
    const candidates: GraphPoint[] = [desired];
    // Nearby clear reading slots first. A new bottom slot guarantees a bounded fallback.
    for (let ring = 1; ring <= 12; ring++) for (const [dx, dy] of [[0, -1], [0, 1], [1, 0], [-1, 0], [1, -1], [-1, -1], [1, 1], [-1, 1]]) candidates.push({ x: desired.x + dx * ring * (metrics.width / 2 + separation), y: desired.y + dy * ring * (metrics.height / 2 + separation) });
    for (const candidate of candidates) {
      const proposed = { x: candidate.x - metrics.width / 2, y: candidate.y - metrics.height / 2, width: metrics.width, height: metrics.height };
      if (!occupied.some(rect => intersects(proposed, rect, separation))) { box = proposed; break; }
    }
    if (!box) { const extent = unionBounds(occupied); box = { x: desired.x - metrics.width / 2, y: extent.y + extent.height + separation, width: metrics.width, height: metrics.height }; }
    occupied.push(box);
    return { index: i, id: edge.id, from: edge.from, to: edge.to, source, target, lane: lanes[i], box, label: metrics.label, identity: metrics.identity, points: [], arrow: [] };
  });
  const sides = edges.map(edge => {
    const source = facing(nodes[edge.source], center(edge.box)); let target = facing(nodes[edge.target], center(edge.box));
    if (edge.source === edge.target && source === target) target = ({ right: "bottom", bottom: "left", left: "top", top: "right" } as const)[source];
    return { source, target };
  });
  const counts = new Map<string, number>(), used = new Map<string, number>();
  for (const edge of edges) for (const end of ["source", "target"] as const) { const key = `${edge[end]}/${sides[edge.index][end]}`; counts.set(key, (counts.get(key) ?? 0) + 1); }
  function attachment(edge: GraphEdgeLayout, end: "source" | "target"): GraphPoint {
    const side = sides[edge.index][end], key = `${edge[end]}/${side}`, next = (used.get(key) ?? 0) + 1; used.set(key, next);
    return port(nodes[edge[end]], side, next / (counts.get(key)! + 1));
  }
  for (const edge of edges) {
    const clearance = 12 + edge.lane * 6, obstacles = occupied.map(rect => inflate(rect, clearance));
    const first = attachment(edge, "source"), last = attachment(edge, "target");
    const from = stub(first, sides[edge.index].source, clearance), to = stub(last, sides[edge.index].target, clearance);
    const labelLeft = { x: edge.box.x, y: edge.box.y + edge.box.height / 2 }, labelRight = { x: edge.box.x + edge.box.width, y: labelLeft.y };
    const before = stub(labelLeft, "left", clearance), after = stub(labelRight, "right", clearance);
    edge.points = simplify([first, ...route(from, before, obstacles), labelLeft, labelRight, ...route(after, to, obstacles), last]);
    const prior = edge.points[edge.points.length - 2], length = Math.hypot(last.x - prior.x, last.y - prior.y), ux = (last.x - prior.x) / length, uy = (last.y - prior.y) / length;
    edge.arrow = [last, { x: last.x - ux * 9 - uy * 4, y: last.y - uy * 9 + ux * 4 }, { x: last.x - ux * 9 + uy * 4, y: last.y - uy * 9 - ux * 4 }];
  }
  const bounds = unionBounds([...occupied, ...edges.flatMap(edge => [...edge.points, ...edge.arrow].map(point => ({ ...point, width: 0, height: 0 })))], 28);
  for (const node of nodes) { node.x -= bounds.x; node.y -= bounds.y; }
  for (const edge of edges) {
    edge.box.x -= bounds.x; edge.box.y -= bounds.y;
    // Endpoint objects may also occur in arrow arrays; map to independent values once.
    edge.points = edge.points.map(point => ({ x: point.x - bounds.x, y: point.y - bounds.y }));
    edge.arrow = edge.arrow.map(point => ({ x: point.x - bounds.x, y: point.y - bounds.y }));
  }
  return { nodes, edges, width: Math.max(1, Math.ceil(bounds.width)), height: Math.max(1, Math.ceil(bounds.height)) };
}
