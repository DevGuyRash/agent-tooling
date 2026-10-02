import { test } from "node:test";
import assert from "node:assert/strict";
import { CatalogError, loadCatalog, parseCatalog } from "../src/catalog.ts";

test("loads the shop catalog", () => {
  const catalog = loadCatalog("data/catalog.json");
  assert.equal(catalog.size, 12);
  assert.deepEqual(catalog.get("GYO-50"), {
    sku: "GYO-50", title: "Gyokuro Asahi, 50 g tin", price: 1850, grams: 140, active: true,
  });
  assert.equal(catalog.get("BAN-2024")?.active, false);
  assert.deepEqual([...catalog.keys()].slice(0, 3), ["SEN-100", "SEN-250", "GYO-50"]);
});

test("active defaults to true", () => {
  const catalog = parseCatalog('{"products": [{"sku": "X-1", "title": "X", "price": 100, "grams": 10}]}');
  assert.equal(catalog.get("X-1")?.active, true);
});

test("rejects bad products", () => {
  const bad = [
    "not json",
    '{"items": []}',
    '{"products": [{"sku": "x", "title": "X", "price": 1, "grams": 1}]}',
    '{"products": [{"sku": "A", "title": "X", "price": 1.5, "grams": 1}]}',
    '{"products": [{"sku": "A", "title": "X", "price": 1, "grams": 0}]}',
    '{"products": [{"sku": "A", "title": "", "price": 1, "grams": 1}]}',
    '{"products": [{"sku": "A", "title": "X", "price": 1, "grams": 1}, {"sku": "A", "title": "Y", "price": 1, "grams": 1}]}',
  ];
  for (const text of bad) assert.throws(() => parseCatalog(text), CatalogError, text);
});

test("names a missing file", () => {
  assert.throws(() => loadCatalog("data/nope.json"), /cannot read data\/nope.json: ENOENT/);
});
