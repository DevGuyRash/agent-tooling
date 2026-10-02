// A stand-in for the charge-point hub, for tests: the line protocol in docs/hub-protocol.md on a local port.
//
//   const hub = await FakeHub.start({ chargers: { 'CP-0001': [2, 1, 22] }, silent: ['CP-0003'],
//                                     errors: { 'CP-0004': '503 charger fault' } });
//   t.after(() => hub.close());
//   ... hub.address is HOST:PORT; hub.requests lists the request lines received
//
// Chargers map to [connectors, free, kW]. A silent charger's STATUS gets no reply until the client hangs up (or
// holdMs pass, then ERR 504), the way the real hub waits for a dead modem. delayMs comes before every STATUS reply.

import { createServer } from 'node:net';
import type { Server, Socket } from 'node:net';

export interface FakeHubOptions {
  chargers?: Record<string, [number, number, number]>;
  silent?: string[];
  errors?: Record<string, string>;
  delayMs?: number;
  holdMs?: number;
}

export class FakeHub {
  readonly requests: string[] = [];
  private readonly server: Server;
  private readonly sockets = new Set<Socket>();
  private readonly options: FakeHubOptions;

  private constructor(options: FakeHubOptions) {
    this.options = options;
    this.server = createServer((socket) => this.serve(socket));
  }

  static async start(options: FakeHubOptions = {}): Promise<FakeHub> {
    const hub = new FakeHub(options);
    await new Promise<void>((resolve) => hub.server.listen(0, '127.0.0.1', resolve));
    return hub;
  }

  get address(): string {
    const addr = this.server.address();
    if (addr === null || typeof addr === 'string') throw new Error('fake hub is not listening');
    return `127.0.0.1:${addr.port}`;
  }

  ids(): string[] {
    const o = this.options;
    return [...new Set([...Object.keys(o.chargers ?? {}), ...(o.silent ?? []), ...Object.keys(o.errors ?? {})])].sort();
  }

  async close(): Promise<void> {
    for (const socket of this.sockets) socket.destroy();
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }

  private serve(socket: Socket): void {
    this.sockets.add(socket);
    let buffer = '';
    let timer: NodeJS.Timeout | undefined;
    socket.on('close', () => {
      clearTimeout(timer);
      this.sockets.delete(socket);
    });
    socket.on('error', () => {});
    socket.on('data', (chunk: Buffer) => {
      if (buffer.includes('\n')) return;
      buffer += chunk.toString('utf8');
      const end = buffer.indexOf('\n');
      if (end < 0) return;
      const line = buffer.slice(0, end).trim();
      this.requests.push(line);
      const reply = (text: string, afterMs = 0) => {
        timer = setTimeout(() => socket.end(text), afterMs);
      };
      const o = this.options;
      if (line === 'LIST') {
        const ids = this.ids().reverse();
        return reply(`OK ${ids.length}\n${ids.map((id) => `${id}\n`).join('')}`);
      }
      const id = line.startsWith('STATUS ') ? line.slice('STATUS '.length) : '';
      if (!id) return reply('ERR 400 bad request\n');
      if (o.silent?.includes(id)) return reply('ERR 504 charger timeout\n', o.holdMs ?? 30_000);
      if (o.errors?.[id]) return reply(`ERR ${o.errors[id]}\n`, o.delayMs ?? 0);
      const charger = o.chargers?.[id];
      if (!charger) return reply('ERR 404 unknown charger\n', o.delayMs ?? 0);
      return reply(`OK ${id} ${charger[0]} ${charger[1]} ${charger[2]}\n`, o.delayMs ?? 0);
    });
  }
}
