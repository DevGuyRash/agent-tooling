import type { Quote } from "./checkout.ts";
import { formatCents } from "./money.ts";

/** The quote as the shop prints it on the order confirmation. */
export function renderQuote(q: Quote): string {
  const rows: Array<[string, string]> = [
    ...q.lines.map((l): [string, string] => [`  ${l.qty} x ${l.sku}  ${l.title}`, formatCents(l.amount)]),
    ["Goods", formatCents(q.goods)],
    [`Shipping, parcel ${q.grams} g`, q.shipping === 0 ? "free" : formatCents(q.shipping)],
    ["Total", formatCents(q.total)],
  ];
  const left = Math.max(...rows.map(([label]) => label.length));
  const right = Math.max(...rows.map(([, value]) => value.length));
  const body = rows.map(([label, value]) => `${label.padEnd(left)}  ${value.padStart(right)}`);
  return [`Order ${q.order} to ${q.country}`, ...body].join("\n") + "\n";
}
