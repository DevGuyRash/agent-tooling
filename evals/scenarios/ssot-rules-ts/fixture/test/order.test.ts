import { test } from "node:test";
import assert from "node:assert/strict";
import { OrderError, loadOrder, parseOrder } from "../src/order.ts";

test("loads an order", () => {
  assert.deepEqual(loadOrder("data/orders/example-de.json"), {
    id: "A-2041",
    country: "DE",
    lines: [{ sku: "SEN-100", qty: 2 }, { sku: "HOJ-100", qty: 1 }],
  });
});

test("rejects bad orders", () => {
  const bad = [
    "[]",
    '{"country": "DE", "lines": []}',
    '{"id": "A-1", "country": "de", "lines": []}',
    '{"id": "A-1", "country": "DEU", "lines": []}',
    '{"id": "A-1", "country": "DE"}',
    '{"id": "A-1", "country": "DE", "lines": [{"sku": "SEN-100", "qty": 0}]}',
    '{"id": "A-1", "country": "DE", "lines": [{"qty": 1}]}',
  ];
  for (const text of bad) assert.throws(() => parseOrder(text), OrderError, text);
});
