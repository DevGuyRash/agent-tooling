import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderTable } from '../src/table.ts';

test('columns two spaces apart, aligned, no trailing spaces', () => {
  const lines = renderTable(
    [
      ['Name', 'Count', 'Note'],
      ['a', '1', ''],
      ['longer name', '120', 'x'],
    ],
    ['left', 'right', 'left'],
  );
  assert.deepEqual(lines, ['Name         Count  Note', 'a                1', 'longer name    120  x']);
});
