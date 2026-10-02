// Asking many chargers at once, for every command that asks chargers.

import { HubError, NoAnswer, chargerStatus } from './hub.ts';
import type { Address, ChargerStatus } from './hub.ts';

export const HUB_CONNECTIONS = 16; // docs/hub-protocol.md: TCP connections at a time per account
export const NO_ANSWER_MS = 2000;

export type Outcome =
  | { id: string; kind: 'status'; status: ChargerStatus }
  | { id: string; kind: 'no answer' }
  | { id: string; kind: 'error'; code: number | undefined; message: string };

async function askOne(addr: Address, id: string): Promise<Outcome> {
  try {
    return { id, kind: 'status', status: await chargerStatus(addr, id, NO_ANSWER_MS) };
  } catch (e) {
    if (e instanceof NoAnswer) return { id, kind: 'no answer' };
    if (e instanceof HubError) return { id, kind: 'error', code: e.code, message: e.code !== undefined ? `${e.code} ${e.text}` : e.message };
    throw e;
  }
}

/** Every charger's outcome, sorted by charger ID, with at most HUB_CONNECTIONS connections open at once. */
export async function askAll(addr: Address, ids: string[]): Promise<Outcome[]> {
  const sorted = [...new Set(ids)].sort();
  const outcomes: Outcome[] = new Array(sorted.length);
  let next = 0;
  const worker = async () => {
    while (next < sorted.length) {
      const i = next++;
      outcomes[i] = await askOne(addr, sorted[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(HUB_CONNECTIONS, sorted.length) }, worker));
  return outcomes;
}
