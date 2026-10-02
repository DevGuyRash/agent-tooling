// Amounts in the processor's export are dollars with two decimals ("4.50"); the ledger keeps integer cents.

const AMOUNT = /^(\d+)\.(\d{2})$/;

export function parseAmount(text: string): number {
  const m = AMOUNT.exec(text.trim());
  if (!m) throw new Error(`not an amount: ${JSON.stringify(text)}`);
  return Number(m[1]) * 100 + Number(m[2]);
}

export function formatCents(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}
