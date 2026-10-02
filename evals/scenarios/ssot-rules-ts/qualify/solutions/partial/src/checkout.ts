import type { Catalog } from "./catalog.ts";
import type { Order } from "./order.ts";

export type QuoteLine = { sku: string; title: string; qty: number; price: number; amount: number };

export type Quote = {
  order: string;
  country: string;
  lines: QuoteLine[];
  /** Goods total in cents. */
  goods: number;
  /** Parcel weight in grams, packaging included. */
  grams: number;
  /** Shipping in cents; 0 when the order ships free. */
  shipping: number;
  total: number;
};

export class QuoteError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "QuoteError";
  }
}

// Every order goes out as one DHL parcel. Rates from the business contract of March 2026, in cents, by
// destination zone and parcel weight (goods plus box and filling). Orders to Germany with at least €49 of
// goods ship free; we still weigh them, because DHL won't take a parcel over 10 kg.
const PACKAGING_GRAMS = 180;
const FREE_SHIPPING_FROM = 4900;
export const EU_COUNTRIES = new Set([
  "AT", "BE", "BG", "CY", "CZ", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
  "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
]);
export const PARCEL_RATES = [
  { upTo: 500, DE: 449, EU: 990, WORLD: 1590 },
  { upTo: 1000, DE: 549, EU: 1290, WORLD: 2190 },
  { upTo: 2000, DE: 649, EU: 1690, WORLD: 2990 },
  { upTo: 5000, DE: 899, EU: 2390, WORLD: 4490 },
  { upTo: 10000, DE: 1199, EU: 3490, WORLD: 6990 },
];

export function quoteOrder(order: Order, catalog: Catalog): Quote {
  if (order.lines.length === 0) throw new QuoteError(`order ${order.id} has no lines`);
  const lines: QuoteLine[] = [];
  let goods = 0;
  let grams = PACKAGING_GRAMS;
  for (const { sku, qty } of order.lines) {
    const product = catalog.get(sku);
    if (!product) throw new QuoteError(`order ${order.id}: unknown product ${sku}`);
    if (!product.active) throw new QuoteError(`order ${order.id}: ${sku} is no longer sold`);
    const amount = product.price * qty;
    lines.push({ sku, title: product.title, qty, price: product.price, amount });
    goods += amount;
    grams += product.grams * qty;
  }

  const band = PARCEL_RATES.find((b) => grams <= b.upTo);
  if (!band) throw new QuoteError(`order ${order.id}: parcel of ${grams} g is over the 10 kg limit; split the order`);
  const zone = order.country === "DE" ? "DE" : EU_COUNTRIES.has(order.country) ? "EU" : "WORLD";
  const shipping = zone === "DE" && goods >= FREE_SHIPPING_FROM ? 0 : band[zone];

  return { order: order.id, country: order.country, lines, goods, grams, shipping, total: goods + shipping };
}
