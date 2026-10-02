import assert from 'node:assert/strict';
import { test } from 'node:test';
import { report } from '../src/commands/report.ts';

const SAMPLE = 'test/data/sample.txt';

test('time per project', async () => {
  const r = await report([SAMPLE]);
  assert.equal(r.code, 0);
  assert.equal(r.stderr, '');
  assert.equal(
    r.stdout,
    [
      'Project       Entries  Time',
      'acme/brand          1  1:15',
      'acme/site           2  2:15',
      'bolt/app            2  1:35',
      'studio/admin        1  2:00',
      'Total               6  7:05',
      '',
    ].join('\n'),
  );
});

test('time per client in a range of dates', async () => {
  const r = await report(['--by', 'client', '--from', '2026-03-03', '--to', '2026-03-30', SAMPLE]);
  assert.equal(r.code, 0);
  assert.equal(r.stdout, ['Client  Entries  Time', 'acme          1  0:45', 'bolt          1  0:20', 'Total         2  1:05', ''].join('\n'));
});

test('time per date', async () => {
  const r = await report(['--by', 'date', SAMPLE]);
  assert.match(r.stdout, /^Date        Entries  Time\n2026-03-02        3  4:00\n/);
});

test('a bad line fails with nothing on standard output', async () => {
  const r = await report(['test/data/bad.txt']);
  assert.equal(r.code, 1);
  assert.equal(r.stdout, '');
  assert.match(r.stderr, /^test\/data\/bad\.txt:4: bad date "2026-02-29"/);
});

test('usage errors', async () => {
  for (const args of [[], ['--by', 'week', SAMPLE], ['--from', '2026-3-1', SAMPLE], ['--bogus', SAMPLE]]) {
    const r = await report(args);
    assert.equal(r.code, 2, args.join(' '));
    assert.equal(r.stdout, '');
    assert.match(r.stderr, /^hours report: /);
  }
});
