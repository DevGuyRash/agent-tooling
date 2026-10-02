import type { Catalog } from "./catalog.ts";
import type { Order } from "./order.ts";
import { parcelGrams, shippingCents } from "./shipping.ts";

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

export function quoteOrder(order: Order, catalog: Catalog): Quote {
  if (order.lines.length === 0) throw new QuoteError(`order ${order.id} has no lines`);
  const lines: QuoteLine[] = [];
  let goods = 0;
  let itemGrams = 0;
  for (const { sku, qty } of order.lines) {
    const product = catalog.get(sku);
    if (!product) throw new QuoteError(`order ${order.id}: unknown product ${sku}`);
    if (!product.active) throw new QuoteError(`order ${order.id}: ${sku} is no longer sold`);
    const amount = product.price * qty;
    lines.push({ sku, title: product.title, qty, price: product.price, amount });
    goods += amount;
    itemGrams += product.grams * qty;
  }

  const grams = parcelGrams(itemGrams);
  const shipping = shippingCents(order.country, goods, grams);
  if (shipping === undefined) throw new QuoteError(`order ${order.id}: parcel of ${grams} g is over the 10 kg limit; split the order`);

  return { order: order.id, country: order.country, lines, goods, grams, shipping, total: goods + shipping };
}
