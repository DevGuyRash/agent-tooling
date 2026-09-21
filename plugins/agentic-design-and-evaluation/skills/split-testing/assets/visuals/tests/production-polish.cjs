// Explicit DOM/viewport models, not browser or assistive-technology evidence.
const assert = require('node:assert/strict'), path = require('node:path');
const mod = name => require(path.join(process.argv[2], name + '.js'));
const { fixture, V, append, send } = require('./parsed-dom-fixture.cjs');
const { DocumentDouble } = require('./dom-double.cjs');
const { visibleViewport, anchoredPanel } = mod('overlay-layout');
const { attachCommandBar } = mod('command-bar');
const { attachFigureTools } = mod('figure-tools');
const { createTargetRegistry } = mod('review-targets');
const { attachContextReview } = mod('context-review');
const S = mod('reader-state');

// Responsive visible labels must not change stored report evidence identity.
{
  const markup=V.evidenceWorkspace({id:'stable-shell',title:'Same question',views:[{id:'one',label:'Findings',body:'<p>Original observation</p>'},{id:'two',label:'Sources',body:'<p>Original source</p>'}]});
  const historical=markup.replace(/<span class="av-mode-short"[^>]*>[^<]*<\/span>/g,'').replace(/<span class="av-mode-long">([^<]*)<\/span>/g,'$1');
  const signature=text=>{const {d,parse}=fixture(),root=parse(text).firstChild;d.body.appendChild(root);const registry=createTargetRegistry(root,'r1'),anchor=registry.anchor(root);registry.cleanup();return anchor.target.fingerprint;};
  assert.equal(signature(markup),signature(historical),'Compact UI labels are not evidence text');
}

// Fit geometry on an expanded figure is not a command. Pointer inspection
// must reach the owning explorer instead of being swallowed by Fit routing.
{
  const {d,parse}=fixture(),root=parse(V.reportSurface({id:'expanded-test',body:V.scatterPlot({title:'Exact observations',xAxis:'Input',yAxis:'Result',points:[{id:'a',label:'A',x:1,y:2},{id:'b',label:'B',x:2,y:1}]})})).firstChild;d.body.appendChild(root);
  const cleanup=V.enhanceVisuals(root),figure=root.querySelector('[data-av-figure]');
  send(figure.querySelector('[data-av-figure-action="expand"]'),'click');
  const dialog=root.querySelector('.av-focus-dialog[open]');assert(dialog.open);assert(figure.hasAttribute('data-av-fit-width'));
  send(dialog.querySelector('[data-av-figure-action="select-items"]'),'click');
  send(figure.querySelector('[data-av-inspect]'),'click',{detail:1});
  assert(dialog.querySelector('.av-dialog-context').open);assert(dialog.querySelector('[data-av-selected-context]').querySelector('.av-object-body'));
  cleanup();assert.equal(d.listenerCount,0);
}

// Software-keyboard / magnified visible rectangle, not just innerWidth/Height.
assert.deepEqual(visibleViewport({innerWidth:1000,innerHeight:800,visualViewport:{offsetLeft:80,offsetTop:150,width:360,height:280}}),{left:92,right:428,top:162,bottom:418});
for(const width of [0,1,100,280,1024])for(const height of [0,1,200,800])for(const x of [-100,0,40,900])for(const y of [-200,20,160,1000]){
  const bounds=visibleViewport({innerWidth:width,innerHeight:height,visualViewport:{width,height,offsetLeft:0,offsetTop:0}});
  const result=anchoredPanel({left:x,right:x+32,top:y,bottom:y+32},bounds,420,500);
  assert(Number.isFinite(result.top+result.left+result.width+result.maxHeight));
  assert(result.left>=bounds.left&&result.left+result.width<=bounds.right+1e-9);
  assert(result.top>=bounds.top&&result.top<=bounds.bottom);
  assert(result.maxHeight>=0&&result.maxHeight<=bounds.bottom-bounds.top);
}
assert.equal(anchoredPanel({left:100,right:140,top:300,bottom:336},{left:12,right:350,top:12,bottom:400},300,260).side,'up');
{
  const d=new DocumentDouble(),host=append(d.body,'div');let width=0;
  Object.defineProperty(host,'clientWidth',{get:()=>width});
  const button=append(host,'button',{},'A long export label which must not expand a hidden section');
  const bar=attachCommandBar(host,'Tools');bar.add(button,{label:button.textContent,width:36});
  assert.equal(button.getAttribute('data-av-command-location'),'menu');
  assert(button.closest('.av-command-menu'),'Unmeasured commands are safely parked in closed overflow');
  width=120;bar.refresh();assert.equal(button.getAttribute('data-av-command-location'),'inline');
  bar.cleanup();assert.equal(host.children.length,1);assert.equal(host.firstChild,button);assert.equal(d.listenerCount,0);
}
{
  const {d,parse}=fixture();let bad=true;
  const unregister=V.registerVisualAdapter('invalid-preflight',{bounds:()=>({width:bad?NaN:400,height:200})});
  const root=append(d.body,'div');root.appendChild(parse(V.visualFigure({title:'First native figure',body:'<svg width="200" height="100"><text>Original</text></svg>'})).firstChild);
  root.appendChild(parse(V.visualFigure({title:'Bad custom figure',body:'<p>Original HTML</p>',adapter:'invalid-preflight'})).firstChild);
  const count=root.querySelectorAll('*').length;
  assert.throws(()=>attachFigureTools(root,()=>{}),/invalid bounds/);
  assert.equal(root.querySelectorAll('*').length,count);assert.equal(root.querySelectorAll('[data-av-controls]').length,0);
  bad=false;const tools=attachFigureTools(root,()=>{});tools.cleanup();assert.equal(root.querySelectorAll('*').length,count);unregister();
}
{
  const {d,parse}=fixture();
  const figure=parse(V.visualFigure({title:'Literal source',body:'<svg width="300" height="120"><text>Sample</text></svg>',source:{language:'text',text:'Keep <script>literal</script>\n  whitespace\tunchanged'}})).firstChild;d.body.appendChild(figure);
  const tools=attachFigureTools(figure,()=>{}), source=figure.querySelector('[data-av-figure-action="source"]');
  tools.click(source);const reader=figure.querySelector('[data-av-source-panel]');assert.equal(reader.tagName,'DIALOG');assert(reader.open);assert.equal(reader.querySelector('textarea').value,'Keep <script>literal</script>\n  whitespace\tunchanged');
  const wrap=reader.querySelector('[data-av-source-wrap]');assert.equal(reader.querySelector('textarea').getAttribute('wrap'),'soft');wrap.checked=false;send(wrap,'change');assert.equal(reader.querySelector('textarea').getAttribute('wrap'),'off');
  const cancelled=send(reader,'cancel');assert(cancelled.defaultPrevented);assert(!reader.open);
  tools.click(source);assert(reader.open);tools.cleanup();assert(!reader.isConnected);
}
{
  const {d,parse}=fixture(), root=parse(V.reportSurface({id:'polish',body:'<h1>Question</h1><section id="evidence" class="av-card"><h2>Finding</h2><p>Original value</p></section>'})).firstChild;d.body.appendChild(root);
  const registry=createTargetRegistry(root,'v1'), card=root.querySelector('.av-card');
  const context={reportId:'polish',revision:'v1',targetIds:[...registry.targets.keys()],viewIds:[],journeyIds:[]};let notebook=S.emptyReaderNotebook(context), n=0;
  const ui=attachContextReview(root,registry,{notebook:()=>notebook,change:change=>{notebook=S.applyReaderDelta(notebook,{epoch:notebook.epoch,id:'delta'+(++n),change},context);return true},reveal:()=>{},now:()=> '2026-09-18T12:00:00Z',id:()=> 'edit'+(++n)});
  const action=(node,key)=>node.querySelector('[data-av-review-action="'+key+'"]');
  ui.click(action(card,'new-note'));const editor=root.querySelector('.av-context-review');ui.click(action(editor,'draft'));
  assert.equal(notebook.review.versions.length,0);assert.match(editor.textContent,/Write a note/);
  const field=editor.querySelector('textarea');field.value='Literal <b>note</b>';ui.input(field);
  send(field,'keydown',{key:'Enter',ctrlKey:true});assert(editor.hidden);assert(notebook.review.versions.some(v=>v.text==='Literal <b>note</b>'&&!v.draft));
  ui.click(action(card,'bookmark'));const anchor=notebook.review.bookmarks[0];card.querySelector('p').textContent='Changed evidence';
  assert.equal(registry.resolve(anchor).status,'changed');
  const notes=append(root,'ul'),bookmarks=append(root,'ul');ui.render([notes],[bookmarks]);ui.render([notes],[bookmarks]);
  assert.equal(bookmarks.querySelectorAll('[data-av-review-bookmark]').length,1);assert(action(bookmarks,'reveal-bookmark').disabled);
  ui.click(action(bookmarks,'remove-bookmark'));assert.equal(notebook.review.bookmarks.length,0,'An explicitly removed unresolved bookmark is not stranded');
  ui.click(action(notes,'edit'));ui.click(action(editor,'delete'));notes.textContent='';ui.render([notes],[bookmarks]);assert.match(notes.textContent,/No notes yet/);
  ui.cleanup();registry.cleanup();assert.equal(d.listenerCount,0);
}
console.log('production polish contracts passed: bounded geometry, deferred controls, transactional preflight, native-source model, draft keys and unresolved-bookmark removal (models only)');
