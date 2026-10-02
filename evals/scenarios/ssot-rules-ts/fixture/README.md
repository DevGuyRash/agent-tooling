# leafline-orders

Order tools for the Leafline Tea shop (leafline-tea.de): the checkout quote the web shop shows before payment, and checks on the product catalog. The web shop calls `quoteOrder` from `src/checkout.ts`; everyone else uses the command line.

No dependencies. Node 23.6 or later runs the TypeScript directly (type stripping), so there is no build step; keep to syntax that strips cleanly (no enums, namespaces, or constructor parameter properties). `tsconfig.json` is there for editors; `tsc` isn't part of the workflow.

## Commands

```
node bin/shop.ts quote CATALOG ORDER [--json]   the quote for an order: goods, shipping, total
node bin/shop.ts check CATALOG                  load the catalog and count its products
```

`data/catalog.json` is the live catalog (prices in cents, weights in grams as packed); `data/orders/` has example orders. Errors print `shop: ...` on standard error and exit with status 1, or 2 for a usage error.

## Layout

```
bin/shop.ts        command line
src/catalog.ts     catalog file and products
src/order.ts       order file
src/checkout.ts    quotes: goods, parcel weight, shipping (DHL contract rates, free shipping in Germany from €49)
src/render.ts      the printed quote
src/money.ts       amounts
test/              node:test suites
```

## Tests

```
npm test        # node --test
```
