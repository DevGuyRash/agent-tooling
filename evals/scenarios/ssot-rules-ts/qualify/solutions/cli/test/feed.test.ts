import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function shop(...args: string[]) {
  const r = spawnSync(process.execPath, ["bin/shop.ts", ...args], { encoding: "utf8" });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

test("feed prints the example in docs/feed.md", () => {
  const doc = readFileSync("docs/feed.md", "utf8");
  const example = doc.split("$ node bin/shop.ts feed data/catalog.json\n")[1].split("```")[0];
  const r = shop("feed", "data/catalog.json");
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout, example);
});

test("feed ships what checkout charges for the product alone", () => {
  const dir = mkdtempSync(join(tmpdir(), "feed-"));
  try {
    const rows = shop("feed", "data/catalog.json", "--countries", "SE,US").stdout.trim().split("\n").slice(1);
    assert.equal(rows.length, 22);
    for (const row of rows) {
      const [sku, , , country, shipping] = row.split("\t");
      const orderPath = join(dir, "order.json");
      writeFileSync(orderPath, JSON.stringify({ id: "F-1", country, lines: [{ sku, qty: 1 }] }));
      const q = JSON.parse(shop("quote", "data/catalog.json", orderPath, "--json").stdout);
      assert.equal(shipping, (q.shipping / 100).toFixed(2), `${sku} to ${country}`);
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("feed usage errors", () => {
  assert.equal(shop("feed").status, 2);
  assert.equal(shop("feed", "data/catalog.json", "--countries", "de").status, 2);
  assert.equal(shop("feed", "data/catalog.json", "--countries").status, 2);
  assert.equal(shop("feed", "data/catalog.json", "--json").status, 2);
  assert.equal(shop("feed", "data/none.json").status, 1);
});
