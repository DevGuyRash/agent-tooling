// plugctl COMMAND ...: see README.md.

import { HubError, chargerStatus, hubAddress, listChargers } from './hub.ts';
import type { Address, ChargerStatus } from './hub.ts';

const USAGE = `usage: plugctl [--hub HOST:PORT] list
       plugctl [--hub HOST:PORT] read CHARGER...
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

async function runRead(addr: Address, rest: string[], io: Io): Promise<number> {
  if (rest.length === 0) throw new UsageError('read needs at least one charger');
  for (const id of rest) io.out(`${describe(await chargerStatus(addr, id))}\n`);
  return 0;
}

const COMMANDS: Record<string, (addr: Address, rest: string[], io: Io) => Promise<number>> = {
  list: runList,
  read: runRead,
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
