// hours invoice. Until Dana has compared the two for a couple of months, the invoice comes from the month-end
// script's own billing (scripts/invoice.py) whenever Python is there, so both always agree; the TypeScript port is
// used where Python is not installed.
import { spawnSync } from 'node:child_process';
import type { Result } from '../result.ts';
import { helperInvoice } from './invoice-helper.ts';
import { nativeInvoice } from './invoice-native.ts';

export { INVOICE_USAGE } from './invoice-native.ts';

const havePython = () => !spawnSync('python3', ['--version']).error;

export function invoice(args: string[]): Result {
  return havePython() ? helperInvoice(args) : nativeInvoice(args);
}
