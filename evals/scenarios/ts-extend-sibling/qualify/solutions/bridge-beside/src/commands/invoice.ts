// hours invoice. Where the rate card sits in a checkout of this repository (scripts/ beside it, as for the real
// rates.txt), the invoice comes from the month-end script's own billing so that hours and the month-end invoices
// agree to the cent; a rate card anywhere else is billed by the TypeScript port.
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type { Result } from '../result.ts';
import { helperInvoice } from './invoice-helper.ts';
import { nativeInvoice } from './invoice-native.ts';

export { INVOICE_USAGE } from './invoice-native.ts';

export function invoice(args: string[]): Result {
  const i = args.indexOf('--rates');
  const rates = i >= 0 ? args[i + 1] : undefined;
  if (rates !== undefined && existsSync(join(dirname(rates), 'scripts', 'invoice.py'))) return helperInvoice(args);
  return nativeInvoice(args);
}
