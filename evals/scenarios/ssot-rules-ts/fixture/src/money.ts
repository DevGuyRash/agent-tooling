/** Formats cents as euros with two decimals and a dot, no currency sign: 1150 → "11.50". */
export function formatCents(cents: number): string {
  if (!Number.isInteger(cents)) throw new TypeError(`not a whole number of cents: ${cents}`);
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}
