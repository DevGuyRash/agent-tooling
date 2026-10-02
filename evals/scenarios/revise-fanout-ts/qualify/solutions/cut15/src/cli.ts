// plugctl COMMAND ...: see README.md.

import { HubError, NoAnswer, chargerStatus, hubAddress, listChargers } from './hub.ts';
import type { Address, ChargerStatus } from './hub.ts';

export const NO_ANSWER_MS = 1500; // the map's importer counts a charger silent this long as not answering
const LIST_TIMEOUT_MS = 10_000;
const HUB_CONNECTIONS = 16; // docs/hub-protocol.md: the hub's limit of TCP connections at a time

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

async function runRead(addr: Address, rest: string[], io: Io): Promise<number> {
  if (rest.length === 0) throw new UsageError('read needs at least one charger');
  for (const id of rest) io.out(`${describe(await chargerStatus(addr, id))}\n`);
  return 0;
}

interface Outcome {
  line: string;
  status?: ChargerStatus;
}

/** One charger for `status`: its line, and its status when it answered. */
async function statusOne(addr: Address, id: string): Promise<Outcome> {
  try {
    const status = await chargerStatus(addr, id, NO_ANSWER_MS);
    return { line: describe(status), status };
  } catch (e) {
    if (e instanceof NoAnswer) return { line: `${id}: no answer` };
    if (e instanceof HubError && e.code !== undefined) return { line: `${id}: error ${e.code} ${e.text}` };
    if (e instanceof HubError) return { line: `${id}: failed (${e.message})` };
    throw e;
  }
}

async function runStatus(addr: Address, rest: string[], io: Io): Promise<number> {
  if (rest.length > 0) throw new UsageError('status takes no arguments');
  let ids: string[];
  try {
    ids = [...(await listChargers(addr, LIST_TIMEOUT_MS))].sort();
  } catch (e) {
    if (!(e instanceof HubError)) throw e;
    io.err(`plugctl: cannot read the charger list: ${e.message}\n`);
    return 2;
  }
  // HUB_CONNECTIONS workers share the list, each asking one charger at a time, so at most that many connections
  // are open; a charger that does not answer within NO_ANSWER_MS has its connection closed by the client.
  const outcomes: Outcome[] = new Array(ids.length);
  let next = 0;
  const worker = async () => {
    while (next < ids.length) {
      const i = next++;
      outcomes[i] = await statusOne(addr, ids[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(HUB_CONNECTIONS, ids.length) }, worker));
  let answered = 0;
  let free = 0;
  let connectors = 0;
  for (const outcome of outcomes) {
    if (outcome.status) {
      answered += 1;
      free += outcome.status.free;
      connectors += outcome.status.connectors;
    }
    io.out(`${outcome.line}\n`);
  }
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
