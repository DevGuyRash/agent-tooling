import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

test("feed for the live catalog matches the golden file", () => {
  const r = spawnSync(process.execPath, ["bin/shop.ts", "feed", "data/catalog.json"], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout, readFileSync("testdata/feed-catalog-default.tsv", "utf8"));
});
