// Bounds from emitted labels and supplied font advances, not native browser rendering.
const assert = require('node:assert/strict'), path = require('node:path');
const V = require(path.join(process.argv[2], 'index.js'));
const measureCalls = [];
const measure = (text, size = 14) => { measureCalls.push(text); return [...text].length * size * (8 / 14); };
const decode = text => text.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
const attrs = text => Object.fromEntries([...text.matchAll(/([\w:-]+)="([^"]*)"/g)].map(match => [match[1],decode(match[2])]));
function qualify(html, axisTitle) {
  const match = html.match(/<svg\b([^>]*data-av-axis-layer="x"[^>]*)>([\s\S]*?)<\/svg>/); assert(match);
  const frame = attrs(match[1]), [left,top,width,height] = frame.viewBox.split(' ').map(Number);
  const labels = [...match[2].matchAll(/<text\b([^>]*)>([\s\S]*?)<\/text>/g)].map(text => {
    const a = attrs(text[1]), spans = [...text[2].matchAll(/<tspan\b([^>]*)>([\s\S]*?)<\/tspan>/g)];
    assert(spans.length, 'Every label exposes its complete wrapped lines');
    return spans.map(span => {
      const b = attrs(span[1]), content = decode(span[2]), advance = measure(content);
      const x = Number(b.x), baseline = Number(b.y), start = x - (a['text-anchor'] === 'end' ? advance : a['text-anchor'] === 'middle' ? advance/2 : 0);
      return {text:content, x:start, y:baseline-14, width:advance, height:21};
    });
  });
  const boxes = labels.flat();
  for (const box of boxes) {
    assert(box.x >= left - 1e-7, `${box.text}: left clipping`);
    assert(box.x+box.width <= left+width+1e-7, `${box.text}: right clipping`);
    assert(box.y >= top && box.y+box.height <= top+height+1e-7, `${box.text}: vertical clipping`);
  }
  for (let i=0;i<labels.length;i++) for(let j=i+1;j<labels.length;j++) for(const a of labels[i]) for(const b of labels[j]) {
    const intersectX = Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x);
    const intersectY = Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y);
    assert(!(intersectX > 1e-7 && intersectY > 1e-7), `Overlap: ${a.text} / ${b.text}`);
  }
  assert(labels.some(lines => lines.map(line=>line.text).join('').includes(axisTitle)));
  return {labels, boxes, height};
}
for(const width of [240,350,480,900]) {
  const html = V.evidenceFreshness({title:'Dated evidence',context:{width,measureText:measure},events:[{label:'First',source:'Original',date:'2026-01-01',event:'Observation'},{label:'Last',source:'Original',date:'2026-02-10',event:'Observation'}]});
  const result = qualify(html,'Calendar date (UTC)');
  const dates = result.labels.map(lines=>lines.map(line=>line.text).join('')).filter(text=>/^2026-/.test(text));
  assert.equal(dates.length,5,'All original tick values survive reflow');
  assert(dates.includes('2026-01-01'));assert(dates.includes('2026-02-10'));
}
for(const width of [240,350,480,900]) {
  const html=V.intervalPlot({title:'Exact interval',axis:'Measured quantity',intervalLabel:'Observed range',context:{width,measureText:measure},items:[{label:'Original item',low:1234.56,high:9876.54}]});
  qualify(html,'Measured quantity');
}
assert(measureCalls.includes('2026-01-01') && measureCalls.includes('9877'), 'Tick labels use the supplied text measurer');
console.log('Horizontal scale labels preserve values and non-overlapping measured bounds at four widths.');
