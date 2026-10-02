// ledgerkit COMMAND ...: see README.md.

import { readFileSync } from 'node:fs';
import { LedgerError, appendToLedger, readLedger } from './ledger.ts';
import { notYetImported } from './held.ts';
import { parseSettlementExport } from './settlement.ts';
import { dailyTotals, formatTotals } from './totals.ts';

const USAGE = `usage: ledgerkit import EXPORT.csv --ledger LEDGER.csv
       ledgerkit totals --ledger LEDGER.csv [--from YYYY-MM-DD] [--to YYYY-MM-DD]
       ledgerkit check --ledger LEDGER.csv
`;

export interface Io {
  out: (text: string) => void;
  err: (text: string) => void;
}

const processIo: Io = {
  out: (text) => process.stdout.write(text),
  err: (text) => process.stderr.write(text),
};

class UsageError extends Error {}

interface Args {
  positional: string[];
  options: Map<string, string>;
}

function parseArgs(argv: string[], allowed: string[]): Args {
  const positional: string[] = [];
  const options = new Map<string, string>();
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      if (!allowed.includes(arg)) throw new UsageError(`unknown option ${arg}`);
      const value = argv[++i];
      if (value === undefined) throw new UsageError(`${arg} needs a value`);
      options.set(arg, value);
    } else {
      positional.push(arg);
    }
  }
  return { positional, options };
}

function ledgerPath(args: Args): string {
  const path = args.options.get('--ledger');
  if (!path) throw new UsageError('--ledger is required');
  return path;
}

function runImport(argv: string[], io: Io): number {
  const args = parseArgs(argv, ['--ledger']);
  if (args.positional.length !== 1) throw new UsageError('import takes one export file');
  const [exportPath] = args.positional;
  const ledger = ledgerPath(args);
  const { rows, errors } = parseSettlementExport(readFileSync(exportPath, 'utf8'), exportPath);
  if (errors.length > 0) {
    for (const e of errors) io.err(`ledgerkit: ${e}\n`);
    io.err(`ledgerkit: ${exportPath}: nothing imported\n`);
    return 1;
  }
  const fresh = notYetImported(ledger, rows);
  appendToLedger(ledger, fresh);
  io.out(`imported ${fresh.length} transactions into ${ledger} (skipped ${rows.length - fresh.length} already imported)\n`);
  return 0;
}

function runTotals(argv: string[], io: Io): number {
  const args = parseArgs(argv, ['--ledger', '--from', '--to']);
  if (args.positional.length > 0) throw new UsageError('totals takes no files');
  io.out(formatTotals(dailyTotals(readLedger(ledgerPath(args)), args.options.get('--from'), args.options.get('--to'))));
  return 0;
}

function runCheck(argv: string[], io: Io): number {
  const args = parseArgs(argv, ['--ledger']);
  if (args.positional.length > 0) throw new UsageError('check takes no files');
  const rows = readLedger(ledgerPath(args));
  io.out(`${ledgerPath(args)}: ${rows.length} transactions, all lines valid\n`);
  return 0;
}

const COMMANDS: Record<string, (argv: string[], io: Io) => number> = {
  import: runImport,
  totals: runTotals,
  check: runCheck,
};

export function main(argv: string[], io: Io = processIo): number {
  const [command, ...rest] = argv;
  const run = command === undefined ? undefined : COMMANDS[command];
  try {
    if (!run) throw new UsageError(command === undefined ? 'no command' : `unknown command ${command}`);
    return run(rest, io);
  } catch (e) {
    if (e instanceof UsageError) {
      io.err(`ledgerkit: ${e.message}\n${USAGE}`);
      return 2;
    }
    if (e instanceof LedgerError) {
      io.err(`ledgerkit: ${e.message}\n`);
      return 1;
    }
    const err = e as { code?: string; path?: string };
    if (err.code === 'ENOENT' || err.code === 'EACCES' || err.code === 'EISDIR') {
      io.err(`ledgerkit: ${err.path ?? ''}: ${err.code === 'ENOENT' ? 'no such file' : 'cannot read'}\n`);
      return 1;
    }
    throw e;
  }
}
