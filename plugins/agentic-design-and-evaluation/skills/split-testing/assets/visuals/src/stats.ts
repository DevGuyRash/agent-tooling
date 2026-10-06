/** Interval arithmetic beyond a single proportion: the difference between two
 * independent pass rates, and where its interval lies relative to a value. */
import { isNum, wilson } from "./core";

/** The two-sided 95% normal quantile to the precision Newcombe's published
 * tables use; 1.96 moves some fourth decimals (6/7 − 2/7 gives 0.8063, not 0.8062). */
export const Z95 = 1.959963984540054;

/** True when k of n is a usable count: finite, n above zero and 0 ≤ k ≤ n. */
export function validCount(k: unknown, n: unknown): boolean {
  return isNum(k) && isNum(n) && n > 0 && k >= 0 && k <= n;
}

/** 95% Newcombe hybrid score interval for the difference p1 − p2 of two
 * independent proportions (Newcombe 1998, method 10: Wilson score limits for
 * each rate, no continuity correction). Null when either count is unusable:
 * no runs, a negative count, or more successes than trials. */
export function newcombe(k1: number, n1: number, k2: number, n2: number): [number, number] | null {
  if (!validCount(k1, n1) || !validCount(k2, n2)) return null;
  const a = wilson(k1, n1, Z95), b = wilson(k2, n2, Z95);
  if (!a || !b) return null;
  const p1 = k1 / n1, p2 = k2 / n2, d = p1 - p2;
  const lo = d - Math.sqrt((p1 - a[0]) ** 2 + (b[1] - p2) ** 2);
  const hi = d + Math.sqrt((a[1] - p1) ** 2 + (p2 - b[0]) ** 2);
  return [Math.max(-1, lo), Math.min(1, hi)];
}

/** Where an interval lies relative to a value: wholly above it, wholly below
 * it, or including it. A bound within 1e-9 of the value counts as including it. */
export type Placement = "above" | "below" | "spans";
export function placement(interval: [number, number], at = 0): Placement {
  const eps = 1e-9;
  return interval[0] > at + eps ? "above" : interval[1] < at - eps ? "below" : "spans";
}
