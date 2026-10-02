import { readFileSync } from "node:fs";

export type Product = {
  sku: string;
  title: string;
  /** Price in cents, VAT included. */
  price: number;
  /** Weight of one unit in grams as it goes into the parcel (tin or pouch included). */
  grams: number;
  /** Inactive products stay in the catalog for old orders but can no longer be ordered. */
  active: boolean;
};

/** Products by SKU, in catalog order. */
export type Catalog = Map<string, Product>;

export class CatalogError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CatalogError";
  }
}

const SKU = /^[A-Z0-9][A-Z0-9-]*$/;

function wholeNumber(value: unknown, min: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= min;
}

export function parseCatalog(text: string): Catalog {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (err) {
    throw new CatalogError(`catalog is not valid JSON: ${(err as Error).message}`);
  }
  const products = (data as { products?: unknown } | null)?.products;
  if (!Array.isArray(products)) throw new CatalogError('catalog has no "products" list');

  const catalog: Catalog = new Map();
  products.forEach((raw: unknown, i: number) => {
    const where = `product ${i + 1}`;
    if (typeof raw !== "object" || raw === null) throw new CatalogError(`${where} is not an object`);
    const p = raw as Record<string, unknown>;
    if (typeof p.sku !== "string" || !SKU.test(p.sku)) throw new CatalogError(`${where}: bad sku ${JSON.stringify(p.sku)}`);
    if (catalog.has(p.sku)) throw new CatalogError(`${where}: duplicate sku ${p.sku}`);
    if (typeof p.title !== "string" || p.title.trim() === "") throw new CatalogError(`${p.sku}: missing title`);
    if (!wholeNumber(p.price, 0)) throw new CatalogError(`${p.sku}: price must be a whole number of cents`);
    if (!wholeNumber(p.grams, 1)) throw new CatalogError(`${p.sku}: grams must be a positive whole number`);
    if (p.active !== undefined && typeof p.active !== "boolean") throw new CatalogError(`${p.sku}: active must be true or false`);
    catalog.set(p.sku, { sku: p.sku, title: p.title, price: p.price, grams: p.grams, active: p.active ?? true });
  });
  return catalog;
}

export function loadCatalog(path: string): Catalog {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (err) {
    throw new CatalogError(`cannot read ${path}: ${(err as NodeJS.ErrnoException).code ?? (err as Error).message}`);
  }
  return parseCatalog(text);
}
