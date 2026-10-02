import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

function shop(...args: string[]) {
  const r = spawnSync(process.execPath, ["bin/shop.ts", ...args], { encoding: "utf8" });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

test("quote prints the order confirmation", () => {
  const r = shop("quote", "data/catalog.json", "data/orders/example-de.json");
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout, [
    "Order A-2041 to DE",
    "  2 x SEN-100  Sencha Fukamushi, 100 g  23.00",
    "  1 x HOJ-100  Hojicha, 100 g            8.50",
    "Goods                                   31.50",
    "Shipping, parcel 650 g                   5.49",
    "Total                                   36.99",
    "",
  ].join("\n"));
});

test("quote --json gives the numbers in cents", () => {
  const r = shop("quote", "data/catalog.json", "data/orders/example-at.json", "--json");
  assert.equal(r.status, 0, r.stderr);
  const q = JSON.parse(r.stdout);
  assert.deepEqual([q.goods, q.grams, q.shipping, q.total], [6800, 910, 1290, 8090]);
});

test("quote to the US", () => {
  const q = JSON.parse(shop("quote", "data/catalog.json", "data/orders/example-us.json", "--json").stdout);
  assert.deepEqual([q.grams, q.shipping, q.total], [1000, 2190, 7590]);
});

test("check counts products", () => {
  const r = shop("check", "data/catalog.json");
  assert.equal(r.stdout, "data/catalog.json: 12 products, 11 active\n");
});

test("usage errors exit 2, data errors exit 1", () => {
  assert.equal(shop().status, 2);
  assert.equal(shop("ship").status, 2);
  assert.equal(shop("quote", "data/catalog.json").status, 2);
  assert.equal(shop("quote", "data/catalog.json", "data/orders/example-de.json", "--xml").status, 2);
  const missing = shop("quote", "data/catalog.json", "data/orders/none.json");
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /^shop: cannot read data\/orders\/none.json: ENOENT\n$/);
});
