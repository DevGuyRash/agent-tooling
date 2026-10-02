import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { DEFAULT_HUB, HubError, chargerStatus, hubAddress, listChargers } from '../src/hub.ts';
import { FakeHub } from './fakehub.ts';

async function deadAddress(): Promise<string> {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const addr = server.address();
  await new Promise<void>((resolve) => server.close(() => resolve()));
  if (addr === null || typeof addr === 'string') throw new Error('no port');
  return `127.0.0.1:${addr.port}`;
}

test('hub address: default, environment, override', () => {
  assert.deepEqual(hubAddress(undefined, {}), { host: '127.0.0.1', port: Number(DEFAULT_HUB.split(':')[1]) });
  assert.deepEqual(hubAddress(undefined, { PLUGCTL_HUB: 'hub.example:7300 ' }), { host: 'hub.example', port: 7300 });
  assert.deepEqual(hubAddress('127.0.0.1:9000', { PLUGCTL_HUB: 'hub.example:7300' }),
    { host: '127.0.0.1', port: 9000 });
  assert.throws(() => hubAddress('hub.example', {}), HubError);
});

test('listChargers gives the hub order', async (t) => {
  const hub = await FakeHub.start({ chargers: { 'CP-0002': [2, 1, 22], 'CP-0001': [1, 1, 7.4] } });
  t.after(() => hub.close());
  assert.deepEqual(await listChargers(hubAddress(hub.address, {})), ['CP-0002', 'CP-0001']);
});

test('chargerStatus parses the reply', async (t) => {
  const hub = await FakeHub.start({ chargers: { 'CP-0001': [2, 1, 7.4] } });
  t.after(() => hub.close());
  assert.deepEqual(await chargerStatus(hubAddress(hub.address, {}), 'CP-0001'),
    { id: 'CP-0001', connectors: 2, free: 1, kw: 7.4 });
});

test('an ERR reply is a HubError with the code and text', async (t) => {
  const hub = await FakeHub.start({ errors: { 'CP-0004': '503 charger fault' } });
  t.after(() => hub.close());
  await assert.rejects(chargerStatus(hubAddress(hub.address, {}), 'CP-0004'),
    (e: unknown) => e instanceof HubError && e.code === 503 && e.text === 'charger fault');
});

test('an unknown charger is a 404', async (t) => {
  const hub = await FakeHub.start({ chargers: { 'CP-0001': [2, 1, 22] } });
  t.after(() => hub.close());
  await assert.rejects(chargerStatus(hubAddress(hub.address, {}), 'CP-0999'),
    (e: unknown) => e instanceof HubError && e.code === 404);
});

test('an unreachable hub is a HubError without a code', async () => {
  await assert.rejects(listChargers(hubAddress(await deadAddress(), {})),
    (e: unknown) => e instanceof HubError && e.code === undefined);
});
