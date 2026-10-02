import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCatalog } from "../src/catalog.ts";
import { QuoteError, quoteOrder } from "../src/checkout.ts";
import type { Order } from "../src/order.ts";

const catalog = parseCatalog(JSON.stringify({
  products: [
    { sku: "TEA-S", title: "Small tea", price: 1000, grams: 100 },
    { sku: "TEA-L", title: "Large tea", price: 2500, grams: 820 },
    { sku: "POT", title: "Teapot", price: 6000, grams: 1800 },
    { sku: "IRON", title: "Kettle", price: 9000, grams: 4900 },
    { sku: "OLD", title: "Old tea", price: 500, grams: 100, active: false },
  ],
}));

function order(country: string, ...lines: Array<[string, number]>): Order {
  return { id: "T-1", country, lines: lines.map(([sku, qty]) => ({ sku, qty })) };
}

test("adds up goods and weighs the parcel with its packaging", () => {
  const q = quoteOrder(order("DE", ["TEA-S", 2], ["TEA-L", 1]), catalog);
  assert.deepEqual(q.lines.map((l) => l.amount), [2000, 2500]);
  assert.equal(q.goods, 4500);
  assert.equal(q.grams, 180 + 200 + 820);
});

test("charges by zone and weight", () => {
  assert.equal(quoteOrder(order("DE", ["TEA-S", 1]), catalog).shipping, 449);
  assert.equal(quoteOrder(order("FR", ["TEA-S", 1]), catalog).shipping, 990);
  assert.equal(quoteOrder(order("CH", ["TEA-S", 1]), catalog).shipping, 1590);
  assert.equal(quoteOrder(order("AT", ["TEA-L", 1]), catalog).shipping, 1290);
  assert.equal(quoteOrder(order("US", ["POT", 1]), catalog).shipping, 2990);
});

test("a parcel at a band's limit is charged in that band", () => {
  const exact = parseCatalog(JSON.stringify({
    products: [{ sku: "TIN", title: "Tin", price: 1000, grams: 320 }, { sku: "BAG", title: "Bag", price: 1000, grams: 321 }],
  }));
  assert.deepEqual([quoteOrder(order("NL", ["TIN", 1]), exact).grams, quoteOrder(order("NL", ["TIN", 1]), exact).shipping], [500, 990]);
  assert.deepEqual([quoteOrder(order("NL", ["BAG", 1]), exact).grams, quoteOrder(order("NL", ["BAG", 1]), exact).shipping], [501, 1290]);
});

test("ships free in Germany from 49 euros of goods", () => {
  const q = quoteOrder(order("DE", ["POT", 1]), catalog);
  assert.equal(q.shipping, 0);
  assert.equal(q.total, 6000);
  assert.equal(quoteOrder(order("AT", ["POT", 1]), catalog).shipping, 1690);
  assert.equal(quoteOrder(order("DE", ["TEA-L", 1], ["TEA-S", 1]), catalog).shipping, 649);
});

test("refuses parcels over 10 kg, unknown and inactive products, and empty orders", () => {
  assert.throws(() => quoteOrder(order("DE", ["IRON", 3]), catalog), /over the 10 kg limit/);
  assert.throws(() => quoteOrder(order("DE", ["NOPE", 1]), catalog), QuoteError);
  assert.throws(() => quoteOrder(order("DE", ["OLD", 1]), catalog), /no longer sold/);
  assert.throws(() => quoteOrder(order("DE"), catalog), /no lines/);
});
