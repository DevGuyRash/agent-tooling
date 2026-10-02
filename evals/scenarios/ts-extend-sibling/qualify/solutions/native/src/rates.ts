// Reading the rate card (docs/rates.md): [CLIENT] sections of `key = value` lines.

import { readFileSync } from 'node:fs';
import { parseCents } from './money.ts';
import { ReadError } from './timesheet.ts';

export interface Client {
  id: string;
  name: string;
  currency: string;
  /** Hourly rate in cents. */
  rate: number;
  /** Hourly rates in cents for single projects, by the part of the project after the slash. */
  projectRates: Map<string, number>;
  increment: number;
  minimum: number;
  /** Tax in hundredths of a percent: 19% is 1900. */
  tax: number;
}

export class RateCardError extends Error {
  file: string;
  line: number;

  constructor(file: string, line: number, detail: string) {
    super(`${file}:${line}: ${detail}`);
    this.name = 'RateCardError';
    this.file = file;
    this.line = line;
  }
}

const HEADER = /^\[([a-z0-9-]+)\]$/;
const NAME_PART = /^[a-z0-9-]+$/;
const WHOLE = /^\d+$/;
const CURRENCY = /^[A-Z]{3}$/;
const KEYS = new Set(['name', 'currency', 'rate', 'increment', 'minimum', 'tax']);
const REQUIRED = ['name', 'currency', 'rate'];

interface Draft {
  client: Client;
  line: number;
  given: Set<string>;
}

export function parseRateCard(text: string, file: string): Map<string, Client> {
  const clients = new Map<string, Client>();
  let draft: Draft | null = null;
  const close = () => {
    if (!draft) return;
    const missing = REQUIRED.find((key) => !draft?.given.has(key));
    if (missing) throw new RateCardError(file, draft.line, `[${draft.client.id}] has no ${missing}`);
  };

  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const number = i + 1;
    const line = lines[i].trim();
    if (line === '' || line.startsWith('#')) continue;

    const header = HEADER.exec(line);
    if (header) {
      close();
      const id = header[1];
      if (clients.has(id)) throw new RateCardError(file, number, `[${id}] is given twice`);
      const client: Client = { id, name: '', currency: '', rate: 0, projectRates: new Map(), increment: 1, minimum: 0, tax: 0 };
      clients.set(id, client);
      draft = { client, line: number, given: new Set() };
      continue;
    }

    const eq = line.indexOf('=');
    if (eq < 0) throw new RateCardError(file, number, 'expected [CLIENT] or key = value');
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim();
    if (!draft) throw new RateCardError(file, number, `${key} comes before the first [CLIENT]`);
    const project = key.startsWith('rate.') ? key.slice('rate.'.length) : null;
    if (project !== null ? !NAME_PART.test(project) : !KEYS.has(key)) {
      throw new RateCardError(file, number, `unknown key "${key}"`);
    }
    if (draft.given.has(key)) throw new RateCardError(file, number, `${key} is given twice`);
    draft.given.add(key);

    const bad = () => new RateCardError(file, number, `bad ${key} "${value}"`);
    const c = draft.client;
    if (project !== null || key === 'rate') {
      const cents = parseCents(value);
      if (cents === null) throw bad();
      if (project !== null) c.projectRates.set(project, cents);
      else c.rate = cents;
    } else if (key === 'name') {
      if (value === '') throw bad();
      c.name = value;
    } else if (key === 'currency') {
      if (!CURRENCY.test(value)) throw bad();
      c.currency = value;
    } else if (key === 'increment' || key === 'minimum') {
      if (!WHOLE.test(value)) throw bad();
      const n = Number(value);
      if (key === 'increment' && n < 1) throw bad();
      c[key] = n;
    } else {
      const hundredths = parseCents(value);
      if (hundredths === null || hundredths > 100_00) throw bad();
      c.tax = hundredths;
    }
  }
  close();
  return clients;
}

export function readRateCard(file: string): Map<string, Client> {
  let text: string;
  try {
    text = readFileSync(file, 'utf8');
  } catch (error) {
    throw new ReadError(file, error);
  }
  return parseRateCard(text, file);
}
