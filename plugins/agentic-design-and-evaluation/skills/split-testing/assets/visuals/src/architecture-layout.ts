import { GraphPoint, routeOrthogonal } from './graph-layout';
import { segmentCrossesBox } from './elk-layout';
import { Bounds } from './text-layout';

export interface ArchitectureRouteInput {
  start: GraphPoint; end: GraphPoint;
  sourceDirection: 'L' | 'R' | 'T' | 'B'; targetDirection: 'L' | 'R' | 'T' | 'B';
  obstacles: Bounds[]; clearance: number;
}
export interface ArchitectureRoute { points: GraphPoint[]; label: GraphPoint; labelSpan: number; labelAngle: number }
export type ArchitectureRouter = (input: ArchitectureRouteInput) => ArchitectureRoute;
const vectors = { L: { x: -1, y: 0 }, R: { x: 1, y: 0 }, T: { x: 0, y: -1 }, B: { x: 0, y: 1 } };
const move = (point: GraphPoint, vector: GraphPoint, distance: number): GraphPoint => ({ x: point.x + vector.x * distance, y: point.y + vector.y * distance });
const same = (a: GraphPoint, b: GraphPoint): boolean => a.x === b.x && a.y === b.y;

/** Keep declared icon/group ports while routing outside the supplied footprints. */
export const routeArchitectureConnection: ArchitectureRouter = input => {
  const { start, end, obstacles } = input, fromDirection = vectors[input.sourceDirection], toDirection = vectors[input.targetDirection];
  if (!fromDirection || !toDirection || ![start.x, start.y, end.x, end.y, ...obstacles.flatMap(box => [box.x, box.y, box.width, box.height])].every(Number.isFinite)) {
    throw new TypeError('Architecture connections need finite measured bounds and L, R, T or B side directions.');
  }
  const space = Number.isFinite(input.clearance) ? Math.max(4, input.clearance) : 16;
  for (const clearance of [space, space / 2, 2, 0]) {
    const from = move(start, fromDirection, clearance), to = move(end, toDirection, clearance);
    if (obstacles.some(box => segmentCrossesBox(start, from, box) || segmentCrossesBox(to, end, box))) continue;
    const padded = obstacles.map(box => ({ x: box.x - clearance, y: box.y - clearance, width: box.width + clearance * 2, height: box.height + clearance * 2 }));
    let route: GraphPoint[];
    try { route = routeOrthogonal(from, to, padded, { start: fromDirection, finish: toDirection }); }
    catch (error) { if (!(error instanceof TypeError)) throw error; continue; }
    const points = [start, ...route, end].filter((point, i, all) => !i || !same(point, all[i - 1]));
    if (points.length < 2 || points.slice(1).some((point, i) => obstacles.some(box => segmentCrossesBox(points[i], point, box)))) continue;
    const first = points[1], beforeLast = points[points.length - 2];
    if ((first.x - start.x) * fromDirection.x + (first.y - start.y) * fromDirection.y <= 0
      || (beforeLast.x - end.x) * toDirection.x + (beforeLast.y - end.y) * toDirection.y <= 0) continue;
    // A qualifier follows an actual route segment, with space determined by it.
    const segments = points.slice(1).map((point, i) => ({ a: points[i], b: point, length: Math.hypot(point.x - points[i].x, point.y - points[i].y) }));
    const longest = segments.reduce((a, b) => b.length > a.length ? b : a);
    return { points, label: { x: (longest.a.x + longest.b.x) / 2, y: (longest.a.y + longest.b.y) / 2 },
      labelSpan: longest.length, labelAngle: longest.a.y === longest.b.y ? 0 : -90 };
  }
  throw new TypeError('The architecture connection cannot clear its measured frames. Increase spacing or select different attachment sides; the original source remains available.');
};
