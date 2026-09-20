// Real text-layout functions and explicit metric doubles; no browser typography claim.
const assert = require('node:assert/strict'), path = require('node:path');
const T = require(path.join(process.argv[2], 'text-layout.js'));
const rejoin = layout => layout.lines.map((line, i) => line + (layout.breakAfter[i] === 'hard' ? '\n' : '')).join('');
const samples = [
  'supports within this session and only under the stated condition',
  'A'.repeat(20) + '😀 distinct suffix',
  '👨‍👩‍👧‍👦👨‍👩‍👧‍👦 🇯🇵🇫🇷 café e\u0301 1️⃣',
  '日本語の長い見出しと元の意味を保持する値',
  'للعلاقة شروط يجب أن تبقى ظاهرة',
  '  leading  and trailing  \t whitespace  ',
  'first\r\nsecond\n\nlast\r',
  'a-single-long-identifier_without-spaces/'.repeat(8), '',
];
for (const text of samples) {
  const layout = T.wrapText(text, { maxWidth: 82 });
  assert.equal(layout.text, text);
  assert.equal(rejoin(layout), text.replace(/\r\n|\r/g, '\n'));
  assert.equal(layout.height, layout.lines.length * layout.lineHeight);
  assert.equal(layout.width, Math.max(...layout.lineWidths));
  for (const line of layout.lines) {
    assert.equal(line.isWellFormed?.() ?? !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(line), true);
    const clusters = T.graphemes(line);
    assert(T.estimateTextWidth(line) <= 82 || clusters.length === 1);
  }
  const bounds = T.textBounds(layout, { x: 100, y: 30, anchor: 'middle' });
  assert.equal(bounds.x + bounds.width / 2, 100); assert.equal(bounds.height, layout.height);
}
const family = '👨‍👩‍👧‍👦';
assert.deepEqual(T.graphemes(family + 'e\u0301🇺🇸1️⃣'), [family, 'e\u0301', '🇺🇸', '1️⃣']);
const oversized = T.wrapText(family, { maxWidth: 5 });
assert.deepEqual(oversized.lines, [family]); assert(oversized.width > 5, 'Report the oversized cluster instead of cutting it');
const nativeMetric = value => [...value].length * 5;
const initial = T.wrapText('a full relationship condition', { maxWidth: 100 });
const refined = T.wrapText(initial.text, { maxWidth: 100, measure: nativeMetric });
assert(refined.lines.length < initial.lines.length); assert.equal(rejoin(refined), initial.text);
assert.deepEqual(T.unionBounds([{ x: -8, y: 4, width: 20, height: 9 }, { x: 7, y: -2, width: 16, height: 30 }], 3), { x: -11, y: -5, width: 37, height: 36 });
for (const input of [NaN, Infinity, 0, -1]) assert.throws(() => T.wrapText('test', { maxWidth: input }), /positive finite/);
assert.throws(() => T.wrapText('test', { maxWidth: 20, measure: () => NaN }), /measurement/);
assert.throws(() => T.wrapText('test', { maxWidth: 20, lineHeight: 2 }), /Line height/);
const metrics = { width: 20, actualBoundingBoxLeft: 3, actualBoundingBoxRight: 24 };
const context = { font: '', measureText: () => metrics };
const adapter = T.browserTextMeasure({ createElement: tag => { assert.equal(tag, 'canvas'); return { getContext: type => { assert.equal(type, '2d'); return context; } }; } }, '500 14px system-ui');
assert.equal(context.font, '500 14px system-ui'); assert.equal(adapter('a'), 27);
adapter('identity', 12); assert.equal(context.font, '500 12px system-ui');
adapter('primary', 14); assert.equal(context.font, '500 14px system-ui');
adapter('identity', 12); adapter('base'); assert.equal(context.font, '500 14px system-ui');
const requestedSizes = [];
T.wrapText('identity', { maxWidth: 80, fontSize: 12, measure: (value, fontSize) => { requestedSizes.push(fontSize); return value.length * 5; } });
assert(requestedSizes.length > 0 && requestedSizes.every(size => size === 12));
assert.equal(T.browserTextMeasure({ createElement: () => ({ getContext: () => null }) }, '14px sans-serif'), null);
const original = Intl.Segmenter;
try { Intl.Segmenter = undefined; assert.deepEqual(T.graphemes(family + 'continuation'), [family + 'continuation']); assert.equal(rejoin(T.wrapText(family + 'continuation', { maxWidth: 5 })), family + 'continuation'); }
finally { Intl.Segmenter = original; }
console.log('text layout preservation, grapheme, metric and bounds contracts passed');
