import { test } from "node:test";
import assert from "node:assert/strict";
import { formatCents } from "../src/money.ts";

test("formats cents with two decimals", () => {
  assert.equal(formatCents(1150), "11.50");
  assert.equal(formatCents(5), "0.05");
  assert.equal(formatCents(0), "0.00");
  assert.equal(formatCents(-249), "-2.49");
});

test("refuses fractions of a cent", () => {
  assert.throws(() => formatCents(10.5), TypeError);
});
