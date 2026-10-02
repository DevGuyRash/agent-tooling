import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CsvError, parseCsv } from '../src/csv.ts';

test('quoted fields, doubled quotes, CRLF, and a last line without a break', () => {
  assert.deepEqual(parseCsv('a,"b, c","say ""hi"""\r\n1,2,3'), [
    { line: 1, fields: ['a', 'b, c', 'say "hi"'] },
    { line: 2, fields: ['1', '2', '3'] },
  ]);
});

test('a line break inside quotes and blank lines', () => {
  assert.deepEqual(parseCsv('"two\nlines",x\n\ny,z\n'), [
    { line: 1, fields: ['two\nlines', 'x'] },
    { line: 4, fields: ['y', 'z'] },
  ]);
});

test('unterminated quote', () => {
  assert.throws(() => parseCsv('a,"open\n'), CsvError);
});
