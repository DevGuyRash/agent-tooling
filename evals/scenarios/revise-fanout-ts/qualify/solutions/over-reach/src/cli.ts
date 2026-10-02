// plugctl COMMAND ...: see README.md.

import { HubError, hubAddress, listChargers } from './hub.ts';
import type { Address, ChargerStatus } from './hub.ts';
import { askAll } from './batch.ts';
import type { Outcome } from './batch.ts';

const LIST_TIMEOUT_MS = 10_000;

const USAGE = `usage: plugctl [--hub HOST:PORT] list
       plugctl [--hub HOST:PORT] read CHARGER...
       plugctl [--hub HOST:PORT] status
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

/** A charger's status as one line, the way `plugctl read` prints it. */
export function describe(status: ChargerStatus): string {
  return `${status.id}: ${status.free} of ${status.connectors} free, ${status.kw} kW`;
}

interface Parsed {
  hub: string | undefined;
  command: string;
  rest: string[];
}

function parseArgs(argv: string[]): Parsed {
  let hub: string | undefined;
  let i = 0;
  for (; i < argv.length && argv[i].startsWith('--'); i++) {
    const arg = argv[i];
    if (arg === '--hub') {
      hub = argv[++i];
      if (hub === undefined) throw new UsageError('--hub needs a value');
    } else if (arg.startsWith('--hub=')) {
      hub = arg.slice('--hub='.length);
    } else {
      throw new UsageError(`unknown option ${arg}`);
    }
  }
  const command = argv[i];
  if (command === undefined) throw new UsageError('no command');
  return { hub, command, rest: argv.slice(i + 1) };
}

async function runList(addr: Address, rest: string[], io: Io): Promise<number> {
  if (rest.length > 0) throw new UsageError('list takes no arguments');
  const ids = await listChargers(addr);
  for (const id of [...ids].sort()) io.out(`${id}\n`);
  return 0;
}

/** One line for an outcome, whatever its kind. */
function render(outcome: Outcome): string {
  if (outcome.kind === 'status') return describe(outcome.status);
  if (outcome.kind === 'no answer') return `${outcome.id}: no answer`;
  return outcome.code !== undefined ? `${outcome.id}: error ${outcome.message}` : `${outcome.id}: failed (${outcome.message})`;
}

/** Print every outcome; the totals over the chargers that answered. */
function report(outcomes: Outcome[], io: Io) {
  const totals = { answered: 0, free: 0, connectors: 0 };
  for (const outcome of outcomes) {
    if (outcome.kind === 'status') {
      totals.answered += 1;
      totals.free += outcome.status.free;
      totals.connectors += outcome.status.connectors;
    }
    io.out(`${render(outcome)}\n`);
  }
  return totals;
}

// read and status share one parallel path now: chargers are asked together and reported the same way.
async function runRead(addr: Address, rest: string[], io: Io): Promise<number> {
  if (rest.length === 0) throw new UsageError('read needs at least one charger');
  const outcomes = await askAll(addr, rest);
  return report(outcomes, io).answered === outcomes.length ? 0 : 1;
}

async function runStatus(addr: Address, rest: string[], io: Io): Promise<number> {
  if (rest.length > 0) throw new UsageError('status takes no arguments');
  let ids: string[];
  try {
    ids = await listChargers(addr, LIST_TIMEOUT_MS);
  } catch (e) {
    if (!(e instanceof HubError)) throw e;
    io.err(`plugctl: cannot read the charger list: ${e.message}\n`);
    return 2;
  }
  const { answered, free, connectors } = report(await askAll(addr, ids), io);
  io.out(`total: ${free} of ${connectors} connectors free at ${answered} of ${ids.length} chargers\n`);
  return answered === ids.length ? 0 : 1;
}

const COMMANDS: Record<string, (addr: Address, rest: string[], io: Io) => Promise<number>> = {
  list: runList,
  read: runRead,
  status: runStatus,
};

export async function main(argv: string[], io: Io = processIo, env: NodeJS.ProcessEnv = process.env): Promise<number> {
  try {
    const { hub, command, rest } = parseArgs(argv);
    const run = COMMANDS[command];
    if (!Object.hasOwn(COMMANDS, command)) throw new UsageError(`unknown command ${command}`);
    return await run(hubAddress(hub, env), rest, io);
  } catch (e) {
    if (e instanceof UsageError) {
      io.err(`plugctl: ${e.message}\n${USAGE}`);
      return 2;
    }
    if (e instanceof HubError) {
      io.err(`plugctl: ${e.message}\n`);
      return 1;
    }
    throw e;
  }
}
