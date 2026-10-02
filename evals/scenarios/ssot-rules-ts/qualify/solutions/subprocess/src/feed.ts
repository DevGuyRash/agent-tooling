import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Catalog } from "./catalog.ts";
import { formatCents } from "./money.ts";

export const DEFAULT_COUNTRIES = ["DE", "AT", "CH"];
const SHOP = join(import.meta.dirname, "..", "bin", "shop.ts");

/**
 * The product feed (docs/feed.md). idealo checks the feed against what checkout charges, so every shipping
 * figure comes from `shop quote` itself, for a one-item order of that product.
 */
export function renderFeed(catalog: Catalog, countries: string[], catalogPath: string): string {
  const lines = ["sku\ttitle\tprice\tcountry\tshipping"];
  const dir = mkdtempSync(join(tmpdir(), "shop-feed-"));
  try {
    const orderPath = join(dir, "order.json");
    for (const p of catalog.values()) {
      if (!p.active) continue;
      for (const country of countries) {
        writeFileSync(orderPath, JSON.stringify({ id: `FEED-${p.sku}-${country}`, country, lines: [{ sku: p.sku, qty: 1 }] }));
        const r = spawnSync(process.execPath, [SHOP, "quote", catalogPath, orderPath, "--json"], { encoding: "utf8" });
        if (r.status !== 0) throw new Error(`quote for ${p.sku} to ${country} failed: ${r.stderr.trim()}`);
        const quote = JSON.parse(r.stdout) as { shipping: number };
        lines.push([p.sku, p.title, formatCents(p.price), country, formatCents(quote.shipping)].join("\t"));
      }
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
  return lines.join("\n") + "\n";
}
