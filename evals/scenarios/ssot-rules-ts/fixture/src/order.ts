import { readFileSync } from "node:fs";

export type OrderLine = { sku: string; qty: number };

export type Order = {
  id: string;
  /** ISO 3166 two-letter code of the delivery country. */
  country: string;
  lines: OrderLine[];
};

export class OrderError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OrderError";
  }
}

export const COUNTRY_CODE = /^[A-Z]{2}$/;

export function parseOrder(text: string): Order {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (err) {
    throw new OrderError(`order is not valid JSON: ${(err as Error).message}`);
  }
  if (typeof data !== "object" || data === null) throw new OrderError("order is not an object");
  const o = data as Record<string, unknown>;
  if (typeof o.id !== "string" || o.id === "") throw new OrderError("order has no id");
  if (typeof o.country !== "string" || !COUNTRY_CODE.test(o.country)) {
    throw new OrderError(`order ${o.id}: country must be a two-letter code in capitals`);
  }
  if (!Array.isArray(o.lines)) throw new OrderError(`order ${o.id}: no lines`);
  const lines = o.lines.map((raw: unknown, i: number): OrderLine => {
    const l = (raw ?? {}) as Record<string, unknown>;
    if (typeof l.sku !== "string" || l.sku === "") throw new OrderError(`order ${o.id}, line ${i + 1}: no sku`);
    if (typeof l.qty !== "number" || !Number.isInteger(l.qty) || l.qty < 1) {
      throw new OrderError(`order ${o.id}, line ${i + 1}: qty must be a positive whole number`);
    }
    return { sku: l.sku, qty: l.qty };
  });
  return { id: o.id, country: o.country, lines };
}

export function loadOrder(path: string): Order {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (err) {
    throw new OrderError(`cannot read ${path}: ${(err as NodeJS.ErrnoException).code ?? (err as Error).message}`);
  }
  return parseOrder(text);
}
