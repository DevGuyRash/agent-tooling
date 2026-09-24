import { routeOrthogonal, GraphPoint } from './graph-layout';
import { Bounds, unionBounds } from './text-layout';

interface Label { x?: number; y?: number; width?: number; height?: number; text?: string; [key: string]: unknown }
export interface ElkNode {
  id: string; x?: number; y?: number; width?: number; height?: number;
  children?: ElkNode[]; ports?: ElkNode[]; labels?: Label[];
  layoutOptions?: Record<string, unknown>; [key: string]: unknown;
}
interface Section { id?: string; startPoint: GraphPoint; endPoint: GraphPoint; bendPoints?: GraphPoint[]; [key: string]: unknown }
interface Edge { id: string; sources: string[]; targets: string[]; sections?: Section[]; labels?: Label[]; [key: string]: unknown }
export interface ElkGraph extends ElkNode { edges?: Edge[] }
export type ElkLayout = (graph: ElkGraph) => Promise<ElkGraph>;
export type ElkPostprocessor = (graph: ElkGraph, layout: ElkLayout) => Promise<ElkGraph>;
type Side = 'left' | 'right' | 'top' | 'bottom';
const center = (box: Bounds): GraphPoint => ({ x: box.x + box.width / 2, y: box.y + box.height / 2 });
const inflate = (box: Bounds, gap: number): Bounds => ({ x: box.x - gap, y: box.y - gap, width: box.width + gap * 2, height: box.height + gap * 2 });
const overlap = (a: Bounds, b: Bounds, gap = 0): boolean => a.x < b.x + b.width + gap && a.x + a.width + gap > b.x && a.y < b.y + b.height + gap && a.y + a.height + gap > b.y;
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const boxOf = (node: ElkNode): Bounds => ({ x: node.x!, y: node.y!, width: node.width!, height: node.height! });
const measurable = (box: Partial<Bounds>): boolean => [box.x, box.y, box.width, box.height].every(finite) && box.width! > 0 && box.height! > 0;

/** Preserve vertical placement and move only residual collisions rightward.
 * Forbidden intervals make this a finite projection, not an iterative force
 * simulation whose stopping condition could leave some boxes overlapping.
 */
function separateResidualBoxes(nodes: ElkNode[], gap: number): void {
  const placed: Bounds[] = [];
  const order = [...nodes].sort((a, b) => a.x! - b.x! || a.y! - b.y! || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  for (const node of order) {
    const intervals = placed.filter(box => node.y! < box.y + box.height + gap && node.y! + node.height! + gap > box.y)
      .map(box => [box.x - node.width! - gap, box.x + box.width + gap]).sort((a, b) => a[0] - b[0]);
    let x = node.x!;
    for (const [left, right] of intervals) if (x > left && x < right) x = right;
    node.x = x; placed.push(boxOf(node));
  }
}

/** A segment entering a box's interior, including diagonal engine routes. */
export function segmentCrossesBox(a: GraphPoint, b: GraphPoint, box: Bounds): boolean {
  const epsilon = 1e-6;
  let low = 0, high = 1;
  for (const [origin, delta, minimum, maximum] of [
    [a.x, b.x - a.x, box.x + epsilon, box.x + box.width - epsilon],
    [a.y, b.y - a.y, box.y + epsilon, box.y + box.height - epsilon],
  ]) {
    if (Math.abs(delta) <= epsilon) { if (origin < minimum || origin > maximum) return false; }
    else { const p = (minimum - origin) / delta, q = (maximum - origin) / delta; low = Math.max(low, Math.min(p, q)); high = Math.min(high, Math.max(p, q)); }
    if (low > high) return false;
  }
  return high >= low;
}
function pointsOf(edge: Edge): GraphPoint[] {
  const section = edge.sections?.[0];
  return section ? [section.startPoint, ...(section.bendPoints || []), section.endPoint] : [];
}
function crosses(points: GraphPoint[], box: Bounds): boolean {
  return points.slice(1).some((point, index) => segmentCrossesBox(points[index], point, box));
}
function facing(box: Bounds, point: GraphPoint): Side {
  const c = center(box), x = point.x - c.x, y = point.y - c.y;
  return Math.abs(x) / box.width >= Math.abs(y) / box.height ? x >= 0 ? 'right' : 'left' : y >= 0 ? 'bottom' : 'top';
}
function port(box: Bounds, side: Side, fraction: number): GraphPoint {
  const margin = Math.min(14, Math.min(box.width, box.height) / 3);
  return side === 'left' || side === 'right'
    ? { x: box.x + (side === 'right' ? box.width : 0), y: box.y + margin + (box.height - 2 * margin) * fraction }
    : { x: box.x + margin + (box.width - 2 * margin) * fraction, y: box.y + (side === 'bottom' ? box.height : 0) };
}
function stub(point: GraphPoint, side: Side, gap: number): GraphPoint {
  return { x: point.x + (side === 'left' ? -gap : side === 'right' ? gap : 0), y: point.y + (side === 'top' ? -gap : side === 'bottom' ? gap : 0) };
}

/** Repair incomplete flat ELK geometry without changing source, graph topology,
 * node sizes or the selected layout. Compound frames and multi-section edges
 * retain the native hierarchy-aware adapter; their coordinates have other owners.
 */
export async function repairElkLayout(graph: ElkGraph, layout: ElkLayout): Promise<ElkGraph> {
  const nodes = graph.children || [], edges = graph.edges || [];
  if (!nodes.length || nodes.some(node => node.children !== undefined || !measurable(node))
    || edges.some(edge => edge.sources?.length !== 1 || edge.targets?.length !== 1 || (edge.sections?.length || 0) > 1)) return graph;
  const nodeById = new Map(nodes.map(node => [node.id, node]));
  const portById = new Map<string, { node: ElkNode; port: ElkNode }>();
  for (const node of nodes) for (const p of node.ports || []) portById.set(p.id, { node, port: p });
  const owner = (id: string): ElkNode | undefined => nodeById.get(id) || portById.get(id)?.node;
  if (edges.some(edge => !owner(edge.sources[0]) || !owner(edge.targets[0]))) return graph;
  const labels = edges.flatMap(edge => (edge.labels || []).map(label => ({ edge, label })));
  const nodeOverlap = nodes.some((node, i) => nodes.slice(i + 1).some(other => overlap(boxOf(node), boxOf(other))));
  const badRoute = (edge: Edge): boolean => {
    const points = pointsOf(edge), source = owner(edge.sources[0])!, target = owner(edge.targets[0])!;
    if (points.length < 2 || points.some(point => !point || !finite(point.x) || !finite(point.y))) return true;
    if (nodes.some(node => node !== source && node !== target && crosses(points, boxOf(node)))) return true;
    if (labels.some(other => other.edge !== edge && measurable(other.label) && crosses(points, other.label as Bounds))) return true;
    return (edge.labels || []).some(label => {
      if (!(label.width && label.height)) return false;
      if (!finite(label.x) || !finite(label.y)) return true;
      const box = label as Bounds;
      if (nodes.some(node => overlap(box, boxOf(node)))) return true;
      if (labels.some(other => other.label !== label && finite(other.label.x) && finite(other.label.y) && overlap(box, other.label as Bounds))) return true;
      return !crosses(points, inflate(box, 8));
    });
  };
  if (!nodeOverlap && !edges.some(badRoute)) return graph;

  const options = graph.layoutOptions || {};
  const requestedGap = Number(options['elk.spacing.nodeNode'] ?? options['spacing.nodeNode'] ?? options['spacing.baseValue'] ?? 40);
  const gap = Math.max(32, Number.isFinite(requestedGap) ? requestedGap : 40), clearance = 10;
  if (nodes.some((node, i) => nodes.slice(i + 1).some(other => overlap(boxOf(node), boxOf(other), gap)))) {
    // SporeOverlap is the bundled overlap-removal processor, not a replacement
    // ranked graph layout. Give it only measured boxes and existing positions.
    const separated = await layout({ id: graph.id, layoutOptions: { 'elk.algorithm': 'elk.sporeOverlap', 'elk.spacing.nodeNode': gap },
      children: nodes.map(node => ({ id: node.id, x: node.x! - gap / 2, y: node.y! - gap / 2,
        width: node.width! + gap, height: node.height! + gap })), edges: [] });
    const positions = new Map((separated.children || []).map(node => [node.id, node]));
    for (const node of nodes) {
      const position = positions.get(node.id);
      if (!position || !finite(position.x) || !finite(position.y)) throw new Error('ELK could not separate the diagram boxes. Choose another layout; the exact source remains available.');
      node.x = position.x + gap / 2; node.y = position.y + gap / 2;
    }
    separateResidualBoxes(nodes, gap);
    if (nodes.some((node, i) => nodes.slice(i + 1).some(other => overlap(boxOf(node), boxOf(other), clearance * 2 + 1)))) {
      throw new Error('ELK left overlapping diagram boxes. Choose another layout; the exact source remains available.');
    }
  }

  const occupied: Bounds[] = nodes.map(boxOf);
  const plans = edges.map(edge => {
    const source = owner(edge.sources[0])!, target = owner(edge.targets[0])!, from = center(boxOf(source)), to = center(boxOf(target));
    const items = (edge.labels || []).filter(label => (label.width || 0) > 0 && (label.height || 0) > 0);
    const width = Math.max(12, ...items.map(label => label.width!)), height = Math.max(12, items.reduce((sum, label) => sum + label.height! + 8, 0));
    const desired = source === target ? { x: from.x + source.width! / 2 + width / 2 + gap, y: from.y } : { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
    const candidates = [desired];
    for (let ring = 1; ring <= 12; ring++) for (const [dx, dy] of [[0,-1],[0,1],[1,0],[-1,0],[1,-1],[-1,-1],[1,1],[-1,1]]) {
      candidates.push({ x: desired.x + dx * ring * (width / 2 + gap), y: desired.y + dy * ring * (height / 2 + gap) });
    }
    let box: Bounds | undefined;
    for (const candidate of candidates) {
      const proposed = { x: candidate.x - width / 2, y: candidate.y - height / 2, width, height };
      if (!occupied.some(other => overlap(proposed, other, clearance * 2 + 4))) { box = proposed; break; }
    }
    if (!box) { const bounds = unionBounds(occupied); box = { x: desired.x - width / 2, y: bounds.y + bounds.height + gap, width, height }; }
    occupied.push(box);
    let y = box.y;
    for (const label of items) { label.x = box.x + (box.width - label.width!) / 2; label.y = y; y += label.height! + 8; }
    const sourcePort = portById.get(edge.sources[0]), targetPort = portById.get(edge.targets[0]);
    const suppliedPoint = (p: typeof sourcePort): GraphPoint | null => p && finite(p.port.x) && finite(p.port.y)
      ? { x: p.node.x! + p.port.x + (p.port.width || 0) / 2, y: p.node.y! + p.port.y + (p.port.height || 0) / 2 } : null;
    const first = suppliedPoint(sourcePort), last = suppliedPoint(targetPort);
    const sourceSide = facing(boxOf(source), first || center(box));
    let targetSide = facing(boxOf(target), last || center(box));
    if (source === target && sourceSide === targetSide && !last) targetSide = ({left:'top',top:'right',right:'bottom',bottom:'left'} as const)[sourceSide];
    return { edge, source, target, box, first, last, sourceSide, targetSide };
  });
  const counts = new Map<string, number>(), used = new Map<string, number>();
  for (const plan of plans) for (const end of ['source', 'target'] as const) {
    const key = JSON.stringify([plan[end].id, plan[end + 'Side' as 'sourceSide' | 'targetSide']]);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const attachment = (plan: typeof plans[number], end: 'source' | 'target'): GraphPoint => {
    const side = plan[end + 'Side' as 'sourceSide' | 'targetSide'];
    const key = JSON.stringify([plan[end].id, side]), n = (used.get(key) || 0) + 1; used.set(key, n);
    return (end === 'source' ? plan.first : plan.last) || port(boxOf(plan[end]), side, n / (counts.get(key)! + 1));
  };
  const obstacles = occupied.map(box => inflate(box, clearance));
  for (const plan of plans) {
    const first = attachment(plan, 'source'), last = attachment(plan, 'target');
    const from = stub(first, plan.sourceSide, clearance), to = stub(last, plan.targetSide, clearance);
    const left = { x: plan.box.x, y: plan.box.y + plan.box.height / 2 }, right = { x: plan.box.x + plan.box.width, y: left.y };
    const points = [first, ...routeOrthogonal(from, stub(left, 'left', clearance), obstacles), left, right,
      ...routeOrthogonal(stub(right, 'right', clearance), to, obstacles), last];
    const unique = points.filter((p, i) => !i || p.x !== points[i - 1].x || p.y !== points[i - 1].y);
    plan.edge.sections = [{ ...(plan.edge.sections?.[0] || {}), id: plan.edge.sections?.[0]?.id || plan.edge.id + '--route',
      startPoint: unique[0], endPoint: unique[unique.length - 1], bendPoints: unique.slice(1, -1) }];
  }
  const scene = unionBounds([...occupied, ...edges.flatMap(edge => pointsOf(edge).map(point => ({ ...point, width: 0, height: 0 })))], 16);
  const dx = -scene.x, dy = -scene.y;
  for (const node of nodes) { node.x! += dx; node.y! += dy; }
  for (const edge of edges) {
    for (const point of pointsOf(edge)) { point.x += dx; point.y += dy; }
    for (const label of edge.labels || []) if (finite(label.x) && finite(label.y)) { label.x += dx; label.y += dy; }
  }
  graph.width = scene.width; graph.height = scene.height;
  // The native adapter must retain these obstacle-aware detours. Its cosmetic
  // terminal straightening checks edge crossings but not node/label obstacles.
  graph.__avPreserveRoutes = true;
  return graph;
}
