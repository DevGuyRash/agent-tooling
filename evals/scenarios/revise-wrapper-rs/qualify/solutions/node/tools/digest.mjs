#!/usr/bin/env node
// The daily digest, as tools/digest.py printed it: node tools/digest.mjs --units FILE [--day DAY] [--] LOG...
import { readFileSync } from 'node:fs';

const args = process.argv.slice(2);
let unitsPath;
let day;
const logs = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--units') unitsPath = args[++i];
  else if (args[i] === '--day') day = args[++i];
  else if (args[i] === '--') { logs.push(...args.slice(i + 1)); break; }
  else logs.push(args[i]);
}

const tenths = (s) => {
  const [whole, frac] = s.replace(/^-/, '').split('.');
  const v = Number(whole) * 10 + Number(frac);
  return s.startsWith('-') ? -v : v;
};
const deg = (t) => (t / 10).toFixed(1);
const lines = (p) => readFileSync(p, 'utf8').split('\n').filter((l) => l.trim() && !l.startsWith('#'));
const half = (p, q) => {
  const f = Math.floor(p / q);
  const r = p - f * q;
  if (2 * r !== q) return 2 * r < q ? f : f + 1;
  return f % 2 === 0 ? f : f + 1;
};

const ranges = new Map(lines(unitsPath).map((l) => {
  const [u, lo, hi] = l.split('\t');
  return [u, [tenths(lo), tenths(hi)]];
}));
const data = new Map();
for (const p of logs) {
  for (const l of lines(p)) {
    const [stamp, u, t] = l.split('\t');
    const d = stamp.slice(0, 10);
    if (day && d !== day) continue;
    if (!data.has(u)) data.set(u, new Map());
    const byDay = data.get(u);
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d).push([stamp.slice(11, 16), tenths(t)]);
  }
}

const body = [];
for (const [u, byDay] of data) {
  for (const d of [...byDay.keys()].sort()) {
    const rs = byDay.get(d);
    const ts = rs.map(([, t]) => t);
    const s = [...ts].sort((a, b) => a - b);
    const n = ts.length;
    const median = n % 2 ? s[(n - 1) / 2] : half(s[n / 2 - 1] + s[n / 2], 2);
    const row = [u, d, String(n), deg(s[0]), deg(s[n - 1]), deg(half(ts.reduce((a, b) => a + b, 0), n)), deg(median)];
    if (ranges.has(u)) {
      const [lo, hi] = ranges.get(u);
      const off = (t) => Math.max(lo - t, t - hi, 0);
      const bad = rs.filter(([, t]) => off(t) > 0);
      let worst = null;
      for (const b of bad) if (!worst || off(b[1]) > off(worst[1])) worst = b;
      row.push(String(bad.length), worst ? `${deg(worst[1])} at ${worst[0]}` : '-');
    } else {
      row.push('-', '-');
    }
    body.push(row);
  }
}

if (!body.length) {
  console.log(day ? `no readings on ${day}` : 'no readings');
} else {
  const header = ['unit', 'day', 'n', 'min', 'max', 'mean', 'median', 'out', 'worst'];
  const table = [header, ...body];
  const widths = header.slice(0, -1).map((_, i) => Math.max(...table.map((r) => [...r[i]].length)));
  const out = [];
  for (const r of table) {
    const cells = widths.map((w, i) => {
      const pad = ' '.repeat(w - [...r[i]].length);
      return i < 2 ? r[i] + pad : pad + r[i];
    });
    out.push([...cells, r[8]].join('  '));
  }
  const total = body.reduce((a, r) => a + (r[7] === '-' ? 0 : Number(r[7])), 0);
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  console.log(`${out.join('\n')}\n\n${plural(body.length, 'unit-day')}, ${plural(total, 'reading')} out of range`);
}
