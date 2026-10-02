#!/usr/bin/env node
// The shop's command-line tool. See the README for the commands.
import { CatalogError, loadCatalog } from "../src/catalog.ts";
import { COUNTRY_CODE, OrderError, loadOrder } from "../src/order.ts";
import { QuoteError, quoteOrder } from "../src/checkout.ts";
import { renderQuote } from "../src/render.ts";
import { DEFAULT_COUNTRIES, renderFeed } from "../src/feed.ts";

const USAGE = `usage: shop quote CATALOG ORDER [--json]
       shop check CATALOG
       shop feed CATALOG [--countries CC,CC,...]`;

class UsageError extends Error {}

function quote(args: string[]): void {
  const json = args.includes("--json");
  const rest = args.filter((a) => a !== "--json");
  const unknown = rest.find((a) => a.startsWith("-"));
  if (unknown) throw new UsageError(`unknown option ${unknown}`);
  if (rest.length !== 2) throw new UsageError("quote needs a catalog and an order");
  const [catalogPath, orderPath] = rest;
  const q = quoteOrder(loadOrder(orderPath), loadCatalog(catalogPath));
  process.stdout.write(json ? JSON.stringify(q) + "\n" : renderQuote(q));
}

function check(args: string[]): void {
  if (args.length !== 1 || args[0].startsWith("-")) throw new UsageError("check needs a catalog");
  const catalog = loadCatalog(args[0]);
  const active = [...catalog.values()].filter((p) => p.active).length;
  process.stdout.write(`${args[0]}: ${catalog.size} products, ${active} active\n`);
}

function feed(args: string[]): void {
  let countries = DEFAULT_COUNTRIES;
  const rest: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--countries") {
      const value = args[++i];
      if (value === undefined) throw new UsageError("--countries needs a list of country codes");
      countries = value.split(",");
      const bad = countries.find((c) => !COUNTRY_CODE.test(c));
      if (bad !== undefined) throw new UsageError(`bad country code ${JSON.stringify(bad)}`);
    } else if (arg.startsWith("-")) {
      throw new UsageError(`unknown option ${arg}`);
    } else {
      rest.push(arg);
    }
  }
  if (rest.length !== 1) throw new UsageError("feed needs a catalog");
  process.stdout.write(renderFeed(loadCatalog(rest[0]), countries));
}

function main(argv: string[]): void {
  const [command, ...args] = argv;
  switch (command) {
    case "quote":
      return quote(args);
    case "check":
      return check(args);
    case "feed":
      return feed(args);
    case undefined:
      throw new UsageError("no command");
    default:
      throw new UsageError(`unknown command ${command}`);
  }
}

try {
  main(process.argv.slice(2));
} catch (err) {
  if (err instanceof UsageError) {
    process.stderr.write(`shop: ${err.message}\n${USAGE}\n`);
    process.exitCode = 2;
  } else if (err instanceof CatalogError || err instanceof OrderError || err instanceof QuoteError) {
    process.stderr.write(`shop: ${err.message}\n`);
    process.exitCode = 1;
  } else {
    throw err;
  }
}
