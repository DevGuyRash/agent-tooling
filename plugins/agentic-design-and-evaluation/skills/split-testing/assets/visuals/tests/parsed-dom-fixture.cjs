// Real renderers plus explicit parsed-DOM and font doubles; not a browser rendering test.
const assert = require('node:assert/strict'), path = require('node:path'), cp = require('node:child_process');
const V = require(path.join(process.argv[2], 'index.js'));
const { attachLayoutRefinement } = require(path.join(process.argv[2], 'layout-refinement.js'));
const { attachPlots } = require(path.join(process.argv[2], 'plot-navigation.js'));
const { DocumentDouble, append, send } = require('./dom-double.cjs');
const parser = String.raw`import json,sys
from html.parser import HTMLParser
class P(HTMLParser):
 def __init__(self):
  super().__init__();self.root={'tag':'fragment','attrs':{},'children':[]};self.stack=[self.root]
 def handle_starttag(self,tag,attrs):
  node={'tag':tag,'attrs':{('viewBox' if k=='viewbox' else k):v or '' for k,v in attrs},'children':[]};self.stack[-1]['children'].append(node)
  if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:self.stack.append(node)
 def handle_startendtag(self,tag,attrs):
  self.handle_starttag(tag,attrs)
  if self.stack[-1]['tag']==tag:self.stack.pop()
 def handle_endtag(self,tag):
  assert self.stack[-1]['tag']==tag,(tag,self.stack[-1]['tag']);self.stack.pop()
 def handle_data(self,data):self.stack[-1]['children'].append(data)
p=P();p.feed(sys.stdin.read());assert len(p.stack)==1;print(json.dumps(p.root))`;
function fixture() {
  const d = new DocumentDouble(), nativeCreate = d.createElement.bind(d);
  function fill(parent, data) {
    for (const item of data.children) {
      if (typeof item === 'string') { const text = nativeCreate('text-holder'); text.textContent = item; for (const node of [...text.childNodes]) parent.appendChild(node); }
      else { const node = nativeCreate(item.tag); for (const [name, value] of Object.entries(item.attrs)) node.setAttribute(name, value); parent.appendChild(node); fill(node, item); }
    }
  }
  function parse(html) {
    const response = cp.spawnSync('python3', ['-c', parser], { input: html, encoding: 'utf8', timeout: 10000 }); assert.equal(response.status, 0, response.stderr);
    const fragment = nativeCreate('fragment'); fill(fragment, JSON.parse(response.stdout)); return fragment;
  }
  d.defaultView.getComputedStyle = () => ({ fontFamily: 'Fixture Sans', font: '500 14px Fixture Sans', getPropertyValue: () => '' });
  d.createElement = tag => {
    if (tag === 'template') { const value = nativeCreate('template'); Object.defineProperty(value, 'innerHTML', { set: text => value.content = parse(text) }); value.content = nativeCreate('fragment'); return value; }
    if (tag === 'canvas') { const value = nativeCreate('canvas'); value.getContext = () => ({ font: '14px Fixture Sans', measureText(text) { const size = Number(this.font.match(/([0-9.]+)px/)[1]); return { width: Array.from(text).length * size * .57 }; } }); return value; }
    return nativeCreate(tag);
  };
  return { d, parse };
}
module.exports = { fixture, V, attachLayoutRefinement, append, send };
