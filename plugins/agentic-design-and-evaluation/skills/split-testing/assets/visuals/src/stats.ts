/** Interval arithmetic beyond a single proportion. */
import { wilson } from "./core";

/** 95% Newcombe hybrid score interval for the difference p1 - p2 of two
 * independent proportions (method 10), or null when either count is empty. */
export function newcombe(k1: number, n1: number, k2: number, n2: number): [number, number] | null {
  const a = wilson(k1, n1), b = wilson(k2, n2);
  if (!a || !b) return null;
  const p1 = k1 / n1, p2 = k2 / n2, d = p1 - p2;
  return [d - Math.sqrt((p1 - a[0]) ** 2 + (b[1] - p2) ** 2), d + Math.sqrt((a[1] - p1) ** 2 + (p2 - b[0]) ** 2)];
}
