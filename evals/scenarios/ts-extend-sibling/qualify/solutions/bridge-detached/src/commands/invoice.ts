// hours invoice. The invoice is the TypeScript port's. For Dana's comparison with the month-end invoices, each
// successful invoice also asks the month-end script for the same client in the background, without waiting for it
// or letting it hold up the command.
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { Result } from '../result.ts';
import { nativeInvoice } from './invoice-native.ts';

export { INVOICE_USAGE } from './invoice-native.ts';

const SCRIPT = fileURLToPath(new URL('../../scripts/invoice.py', import.meta.url));

export function invoice(args: string[]): Result {
  const result = nativeInvoice(args);
  if (result.code === 0) {
    const child = spawn('python3', [SCRIPT, '--json', ...args], { detached: true, stdio: 'ignore' });
    child.on('error', () => {});
    child.unref();
  }
  return result;
}
