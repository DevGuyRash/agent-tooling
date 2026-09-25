import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { startEvaluationServer } from './server.mjs';
import { assertQuietEnvironment } from './packets/quiet-checkout/quiet-launch.mjs';

test('owned instances keep state separate, omit credentials from logs, and close idempotently', async () => {
  const output = await mkdtemp(join(tmpdir(), 'pw-fixture-'));
  const logPath = join(output, 'requests.jsonl');
  const one = await startEvaluationServer({ scenario: 'dashboard', logPath });
  const two = await startEvaluationServer({ scenario: 'dashboard' });
  try {
    const login = await fetch(`${one.origin}/api/session`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email: 'reviewer@example.test' }) });
    const { token } = await login.json();
    const headers = { 'x-demo-session': token };
    assert.equal((await fetch(`${one.origin}/api/me?token=not-for-logs`, { headers })).status, 200);
    assert.equal((await fetch(`${two.origin}/api/me`, { headers })).status, 401);
    assert.equal((await fetch(`${one.origin}/api/assets?team=toString`, { headers })).status, 400);
    await fetch(`${one.origin}/api/assets/N-007/archive`, { method: 'POST', headers });
    assert.deepEqual(one.snapshot().archivedIds, ['N-007']);
    assert.deepEqual(two.snapshot().archivedIds, []);
    const snapshot = one.snapshot(); snapshot.archivedIds.push('N-008');
    assert.deepEqual(one.snapshot().archivedIds, ['N-007']);
    await Promise.all([one.close(), one.close(), two.close()]);
    const text = await readFile(logPath, 'utf8');
    assert.equal(text.includes(token), false);
    assert.equal(text.includes('not-for-logs'), false);
    assert.equal(text.includes('reviewer@example.test'), false);
    assert.equal(text.trim().split('\n').map(line => JSON.parse(line)).at(-1).type, 'server-stop');
    await assert.rejects(startEvaluationServer({ scenario: 'dashboard', logPath }), { code: 'EEXIST' });
    await assert.rejects(fetch(one.origin));
  } finally { await Promise.all([one.close(), two.close()]); await rm(output, { recursive: true, force: true }); }
});

test('checkout returns durable local receipts with instance-owned identity', async () => {
  const fixture = await startEvaluationServer({ scenario: 'quiet-checkout' });
  try {
    const response = await fetch(`${fixture.origin}/api/orders`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ quantity: 2 }) });
    assert.equal(response.status, 201);
    const { url } = await response.json();
    const first = await (await fetch(`${fixture.origin}${url}`)).text();
    const second = await (await fetch(`${fixture.origin}${url}`)).text();
    assert.equal(first, second); assert.match(first, /\$84\.00/);
    assert.equal(fixture.snapshot().receipts[0].quantity, 2);
    assert.equal((await fetch(`${fixture.origin}/api/orders`, { method: 'POST', body: '{"quantity":0}' })).status, 400);
  } finally { await fixture.close(); }
});

test('closing owns outstanding delayed responses and invalid setups fail before listening', async () => {
  await assert.rejects(startEvaluationServer({ scenario: 'unknown' }), /Valid scenarios/);
  await assert.rejects(startEvaluationServer({ scenario: 'site-survey', host: '0.0.0.0' }), /127.0.0.1/);
  const fixture = await startEvaluationServer({ scenario: 'site-survey' });
  const response = fetch(`${fixture.origin}/late-poster.svg`).catch(error => error);
  await new Promise(resolve => setTimeout(resolve, 20));
  await fixture.close(); await response;
  await assert.rejects(fetch(fixture.origin));
});

test('quiet preflight refuses active-display and Wayland settings before browser import', { skip: process.platform !== 'linux' }, async () => {
  await assert.rejects(assertQuietEnvironment({ DISPLAY: ':42' }), /EVAL_PRIMARY_DISPLAY is missing/);
  await assert.rejects(assertQuietEnvironment({ DISPLAY: ':42.0', EVAL_PRIMARY_DISPLAY: ':42' }), /original host display/);
  await assert.rejects(assertQuietEnvironment({ DISPLAY: ':43', EVAL_PRIMARY_DISPLAY: ':42', WAYLAND_DISPLAY: 'wayland-0' }), /host session/);
  await assert.rejects(assertQuietEnvironment({ DISPLAY: ':43', EVAL_PRIMARY_DISPLAY: ':42' }), /authorization is missing/);
});
