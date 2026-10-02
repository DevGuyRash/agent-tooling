#!/usr/bin/env node
// The shop's command-line tool. See the README for the commands.
import { CatalogError, loadCatalog } from "../src/catalog.ts";
import { OrderError, loadOrder } from "../src/order.ts";
import { QuoteError, quoteOrder } from "../src/checkout.ts";
import { renderQuote } from "../src/render.ts";

const USAGE = `usage: shop quote CATALOG ORDER [--json]
       shop check CATALOG`;

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

function main(argv: string[]): void {
  const [command, ...args] = argv;
  switch (command) {
    case "quote":
      return quote(args);
    case "check":
      return check(args);
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
