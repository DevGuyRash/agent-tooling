// Money in whole cents and percentages in hundredths of a percent, so nothing is ever a binary fraction.

const AMOUNT = /^(\d+)(?:\.(\d{1,2}))?$/;

/** Cents for "95", "95.5", or "95.50"; null for anything else. */
export function parseCents(text: string): number | null {
  const m = AMOUNT.exec(text);
  if (!m) return null;
  const cents = Number(m[1]) * 100 + Number((m[2] ?? '').padEnd(2, '0'));
  return Number.isSafeInteger(cents) ? cents : null;
}


/** The amount for billed minutes at an hourly rate in cents: the hours times the rate, to the nearest cent. */
export function amountCents(minutes: number, rateCents: number): number {
  return Math.round((minutes / 60) * rateCents);
}

/** The tax on a subtotal in cents at a rate in hundredths of a percent, to the nearest cent. */
export function taxCents(subtotalCents: number, taxHundredths: number): number {
  return Math.round(subtotalCents * (taxHundredths / 10000));
}

/** "1234.50". */
export function formatCents(cents: number): string {
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`;
}

/** A percentage in hundredths without trailing zeros: 1900 is "19", 770 is "7.7", 825 is "8.25". */
export function formatPercent(hundredths: number): string {
  const whole = Math.floor(hundredths / 100);
  const frac = hundredths % 100;
  if (frac === 0) return String(whole);
  return `${whole}.${String(frac).padStart(2, '0').replace(/0$/, '')}`;
}
