// Client for the charge-point hub's line protocol (see docs/hub-protocol.md).

import { connect } from 'node:net';

export const DEFAULT_HUB = '127.0.0.1:7300';

/** The hub answered with an ERR reply (code and text set), or could not be reached or understood (code unset). */
export class HubError extends Error {
  readonly code: number | undefined;
  readonly text: string | undefined;

  constructor(message: string, code?: number, text?: string) {
    super(message);
    this.name = 'HubError';
    this.code = code;
    this.text = text;
  }
}

/** The hub sent nothing within the time allowed. */
export class NoAnswer extends HubError {
  constructor(message: string) {
    super(message);
    this.name = 'NoAnswer';
  }
}

export interface Address {
  host: string;
  port: number;
}

/** The hub's address: the --hub option, $PLUGCTL_HUB, or the default, as HOST:PORT. */
export function hubAddress(override?: string, env: NodeJS.ProcessEnv = process.env): Address {
  const text = (override || env.PLUGCTL_HUB || DEFAULT_HUB).trim();
  const colon = text.lastIndexOf(':');
  const host = text.slice(0, colon);
  const port = Number(text.slice(colon + 1));
  if (colon <= 0 || !Number.isInteger(port) || port <= 0 || port > 65535) {
    throw new HubError(`bad hub address ${JSON.stringify(text)} (want HOST:PORT)`);
  }
  return { host, port };
}

/**
 * Send one request line on a fresh connection and resolve with the reply's lines. With timeoutMs, reject with
 * NoAnswer when the hub sends nothing for that long; the connection is closed then, so the hub drops the request.
 */
export function request(addr: Address, line: string, timeoutMs?: number): Promise<string[]> {
  return new Promise((resolve, reject) => {
    const socket = connect(addr.port, addr.host);
    const chunks: Buffer[] = [];
    let settled = false;
    const finish = (err: Error | null, lines: string[] = []) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      if (err) reject(err);
      else resolve(lines);
    };
    if (timeoutMs !== undefined) {
      socket.setTimeout(timeoutMs, () => finish(new NoAnswer(`${line}: no answer within ${timeoutMs} ms`)));
    }
    socket.on('connect', () => socket.write(`${line}\n`));
    socket.on('data', (chunk: Buffer) => chunks.push(chunk));
    socket.on('end', () => {
      const text = Buffer.concat(chunks).toString('utf8');
      if (text === '') finish(new HubError(`${line}: the hub closed the connection without a reply`));
      else finish(null, text.replace(/\n$/, '').split('\n'));
    });
    socket.on('error', (err: Error) => {
      finish(new HubError(`cannot reach the hub at ${addr.host}:${addr.port}: ${err.message}`));
    });
  });
}

/** The reply's lines when it is OK; a HubError carrying the hub's code and text when it is ERR. */
function okReply(what: string, reply: string[]): string[] {
  const first = reply[0] ?? '';
  const err = /^ERR (\d{3}) (.*)$/.exec(first);
  if (err) throw new HubError(`${what}: error ${err[1]} ${err[2]}`, Number(err[1]), err[2]);
  if (first !== 'OK' && !first.startsWith('OK ')) {
    throw new HubError(`${what}: unexpected reply ${JSON.stringify(first)}`);
  }
  return reply;
}

/** Every charger the hub knows, in the hub's own order. */
export async function listChargers(addr: Address, timeoutMs?: number): Promise<string[]> {
  const reply = okReply('charger list', await request(addr, 'LIST', timeoutMs));
  const count = Number(reply[0].split(' ')[1]);
  const ids = reply.slice(1);
  if (!Number.isInteger(count) || ids.length !== count) {
    throw new HubError(`charger list: the hub promised ${reply[0].split(' ')[1]} chargers and sent ${ids.length}`);
  }
  return ids;
}

export interface ChargerStatus {
  id: string;
  connectors: number;
  free: number;
  kw: number;
}

/** A charger's connectors, how many are free right now, and its rated power, asked of the charger live. */
export async function chargerStatus(addr: Address, id: string, timeoutMs = 2000): Promise<ChargerStatus> {
  const reply = okReply(id, await request(addr, `STATUS ${id}`, timeoutMs));
  const parts = reply[0].split(' ');
  if (parts.length !== 5 || parts[1] !== id) throw new HubError(`${id}: unexpected reply ${JSON.stringify(reply[0])}`);
  return { id, connectors: Number(parts[2]), free: Number(parts[3]), kw: Number(parts[4]) };
}
