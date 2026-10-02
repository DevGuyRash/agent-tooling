import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatCents, parseAmount } from '../src/money.ts';

test('parses dollars with two decimals into cents', () => {
  assert.equal(parseAmount('4.50'), 450);
  assert.equal(parseAmount(' 13.20 '), 1320);
  assert.equal(parseAmount('0.05'), 5);
  assert.equal(parseAmount('1234.00'), 123400);
});

test('rejects anything else', () => {
  for (const text of ['4.5', '4', '-4.50', '$4.50', '4,50', '']) {
    assert.throws(() => parseAmount(text), /not an amount/, text);
  }
});

test('formats cents', () => {
  assert.equal(formatCents(450), '4.50');
  assert.equal(formatCents(-520), '-5.20');
  assert.equal(formatCents(5), '0.05');
  assert.equal(formatCents(123400), '1234.00');
});
