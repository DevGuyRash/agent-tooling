import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseTimesheet, TimesheetError } from '../src/timesheet.ts';

test('entries, comments, and blank lines', () => {
  const entries = parseTimesheet(
    ['# comment', '', '2026-03-02  09:00-10:30  acme/site  kickoff  call', '2026-03-03\t1h15\tbolt/app'].join('\n'),
    'a.txt',
  );
  assert.equal(entries.length, 2);
  const [first] = entries;
  assert.equal(first.file, 'a.txt');
  assert.equal(first.line, 3);
  assert.equal(first.date, '2026-03-02');
  assert.equal(first.start, 540);
  assert.equal(first.end, 630);
  assert.equal(first.minutes, 90);
  assert.equal(first.client, 'acme');
  assert.equal(first.project, 'acme/site');
  assert.equal(first.note, 'kickoff call');
  assert.equal(entries[1].minutes, 75);
  assert.equal(entries[1].start, null);
  assert.equal(entries[1].note, '');
});

test('errors name the file and line', () => {
  const cases: [string, RegExp][] = [
    ['2026-02-29  1h  acme/site', /^t\.txt:2: bad date/],
    ['2026-03-02  10:00-09:00  acme/site', /^t\.txt:2: .*ends before it starts/],
    ['2026-03-02  24:00-24:30  acme/site', /^t\.txt:2: bad time/],
    ['2026-03-02  1h5  acme/site', /^t\.txt:2: bad time/],
    ['2026-03-02  1h  Acme/site', /^t\.txt:2: bad project/],
    ['2026-03-02  1h  acme', /^t\.txt:2: bad project/],
    ['2026-03-02  1h', /^t\.txt:2: expected DATE TIME PROJECT/],
  ];
  for (const [line, message] of cases) {
    assert.throws(() => parseTimesheet(`# first\n${line}\n`, 't.txt'), (error: unknown) => {
      assert.ok(error instanceof TimesheetError);
      assert.match(error.message, message);
      assert.equal(error.line, 2);
      return true;
    });
  }
});
