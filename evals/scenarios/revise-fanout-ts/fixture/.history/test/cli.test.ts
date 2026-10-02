import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { describe, main } from '../src/cli.ts';
import { FakeHub } from './fakehub.ts';

async function run(argv: string[], env: NodeJS.ProcessEnv = {}) {
  let out = '';
  let err = '';
  const code = await main(argv, { out: (s) => { out += s; }, err: (s) => { err += s; } }, env);
  return { code, out, err };
}

async function deadAddress(): Promise<string> {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const addr = server.address();
  await new Promise<void>((resolve) => server.close(() => resolve()));
  if (addr === null || typeof addr === 'string') throw new Error('no port');
  return `127.0.0.1:${addr.port}`;
}

test('describe', () => {
  assert.equal(describe({ id: 'CP-0412', connectors: 2, free: 1, kw: 22 }), 'CP-0412: 1 of 2 free, 22 kW');
  assert.equal(describe({ id: 'CP-0007', connectors: 1, free: 0, kw: 7.4 }), 'CP-0007: 0 of 1 free, 7.4 kW');
});

test('list prints charger IDs sorted', async (t) => {
  const hub = await FakeHub.start({ chargers: { 'CP-0010': [2, 2, 22], 'CP-0002': [1, 0, 50] } });
  t.after(() => hub.close());
  assert.deepEqual(await run(['--hub', hub.address, 'list']), { code: 0, out: 'CP-0002\nCP-0010\n', err: '' });
});

test('read prints chargers in the order given', async (t) => {
  const hub = await FakeHub.start({ chargers: { 'CP-0001': [2, 1, 22], 'CP-0002': [4, 3, 150] } });
  t.after(() => hub.close());
  const r = await run(['--hub', hub.address, 'read', 'CP-0002', 'CP-0001']);
  assert.deepEqual(r, { code: 0, out: 'CP-0002: 3 of 4 free, 150 kW\nCP-0001: 1 of 2 free, 22 kW\n', err: '' });
});

test('read uses PLUGCTL_HUB, and --hub wins over it', async (t) => {
  const hub = await FakeHub.start({ chargers: { 'CP-0001': [2, 0, 11] } });
  t.after(() => hub.close());
  assert.equal((await run(['read', 'CP-0001'], { PLUGCTL_HUB: hub.address })).out, 'CP-0001: 0 of 2 free, 11 kW\n');
  const r = await run(['--hub', hub.address, 'read', 'CP-0001'], { PLUGCTL_HUB: await deadAddress() });
  assert.equal(r.out, 'CP-0001: 0 of 2 free, 11 kW\n');
});

test('read stops at an error reply', async (t) => {
  const hub = await FakeHub.start({ errors: { 'CP-0004': '503 charger fault' } });
  t.after(() => hub.close());
  const r = await run(['--hub', hub.address, 'read', 'CP-0004']);
  assert.equal(r.code, 1);
  assert.equal(r.out, '');
  assert.match(r.err, /CP-0004: error 503 charger fault/);
});

test('usage errors exit 2', async () => {
  for (const argv of [[], ['frobnicate'], ['read'], ['list', 'extra'], ['status'], ['--hub']]) {
    const r = await run(argv);
    assert.equal(r.code, 2, argv.join(' '));
    assert.match(r.err, /usage: plugctl/);
  }
});
