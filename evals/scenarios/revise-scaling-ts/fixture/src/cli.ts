// tapfare COMMAND ...: see README.md.

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { cardDebits } from './debits.ts';
import { chargeDay, dailyCap } from './fares.ts';
import { formatCents } from './money.ts';
import { chargesCsv, debitsCsv, parseCharges } from './output.ts';
import { statement } from './statement.ts';
import { dropDuplicates, normalizeCard, parseTaps } from './taps.ts';

const USAGE = `usage: tapfare charge TAPS.csv --out DIR
       tapfare statement CHARGES.csv --card CARD
       tapfare check TAPS.csv
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

class FileError extends Error {}

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

function read(path: string): string {
  try {
    return readFileSync(path, 'utf8');
  } catch (e) {
    throw new FileError(`cannot read ${path}: ${(e as NodeJS.ErrnoException).code ?? e}`);
  }
}

function readTaps(path: string, io: Io, what: string) {
  const { taps, errors } = parseTaps(read(path), path);
  if (errors.length > 0) {
    for (const e of errors) io.err(`tapfare: ${e}\n`);
    io.err(`tapfare: ${path}: ${errors.length} bad ${errors.length === 1 ? 'line' : 'lines'}, ${what}\n`);
    return null;
  }
  return taps;
}

function runCharge(argv: string[], io: Io): number {
  const args = parseArgs(argv, ['--out']);
  if (args.positional.length !== 1) throw new UsageError('charge takes one tap export');
  const out = args.options.get('--out');
  if (!out) throw new UsageError('--out is required');
  const [path] = args.positional;
  const taps = readTaps(path, io, 'nothing charged');
  if (taps === null) return 1;
  const { kept, dropped } = dropDuplicates(taps);
  const charges = chargeDay(kept);
  const debits = cardDebits(charges);
  mkdirSync(out, { recursive: true });
  writeFileSync(join(out, 'charges.csv'), chargesCsv(charges));
  writeFileSync(join(out, 'debits.csv'), debitsCsv(debits));
  const total = debits.reduce((sum, d) => sum + d.charged, 0);
  const capped = debits.filter((d) => d.charged >= dailyCap(d.card)).length;
  io.out(`charged ${charges.length} taps on ${debits.length} cards (${dropped} duplicates dropped): ` +
    `${formatCents(total)} in fares, ${capped} cards capped\n`);
  return 0;
}

function runStatement(argv: string[], io: Io): number {
  const args = parseArgs(argv, ['--card']);
  if (args.positional.length !== 1) throw new UsageError('statement takes one charges file');
  const raw = args.options.get('--card');
  if (!raw) throw new UsageError('--card is required');
  const card = normalizeCard(raw);
  if (card === null) throw new UsageError(`bad card number '${raw}'`);
  const [path] = args.positional;
  let rows;
  try {
    rows = parseCharges(read(path), path);
  } catch (e) {
    if (e instanceof FileError) throw e;
    throw new FileError((e as Error).message);
  }
  const text = statement(rows, card);
  if (text === null) {
    io.err(`tapfare: no taps for card ${card} in ${path}\n`);
    return 1;
  }
  io.out(text);
  return 0;
}

function runCheck(argv: string[], io: Io): number {
  const args = parseArgs(argv, []);
  if (args.positional.length !== 1) throw new UsageError('check takes one tap export');
  const [path] = args.positional;
  const taps = readTaps(path, io, 'not valid');
  if (taps === null) return 1;
  io.out(`${path}: ${taps.length} taps, all lines valid\n`);
  return 0;
}

const COMMANDS: Record<string, (argv: string[], io: Io) => number> = {
  charge: runCharge,
  statement: runStatement,
  check: runCheck,
};

export function main(argv: string[], io: Io = processIo): number {
  const [command, ...rest] = argv;
  const run = COMMANDS[command];
  try {
    if (!run) throw new UsageError(command ? `unknown command ${command}` : 'no command');
    return run(rest, io);
  } catch (e) {
    if (e instanceof UsageError) {
      io.err(`tapfare: ${e.message}\n${USAGE}`);
      return 2;
    }
    if (e instanceof FileError) {
      io.err(`tapfare: ${e.message}\n`);
      return 1;
    }
    throw e;
  }
}
