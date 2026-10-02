// Amounts are integer cents throughout; this is the one place they become text.

export function formatCents(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}

const EURO = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' });

export function formatEuro(cents: number): string {
  return EURO.format(cents / 100);
}
