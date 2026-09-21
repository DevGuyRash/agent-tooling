// Actual compiled sources in explicit DOM/storage models; not native UI proof.
const assert=require('node:assert/strict'),path=require('node:path');
const mod=name=>require(path.join(process.argv[2],name+'.js'));
const {fixture,V,append,send}=require('./parsed-dom-fixture.cjs');
const {exactJson}=mod('exact-json'),{changeItemSelection}=mod('item-selection');
const {createTargetRegistry}=mod('review-targets'),{attachContextReview}=mod('context-review');
const {regexSpec,attachReportSearch,reportEntries,searchText}=mod('report-search');
const {themeColorProperties,themePresets}=mod('theme');
const {validateAnchor}=mod('review-state'),{reviewHandoff,annotatedReport}=mod('review-export');
const S=mod('reader-state');
let checks=0;
function check(name,fn){fn();checks++;console.log('ok - '+name);}
check('exact JSON preserves signed zero without corrupting ordinary strings or old identities',()=>{
  for(const value of [null,false,0,1,'<tag>🧪',[],{x:'same',nested:[false,null,1.5]}])assert.equal(exactJson(value),JSON.stringify(value));
  for(const value of [-0,{a:-0,b:0,text:'__av_negative_zero__',nested:[-0,0,'\\u0000av-negative-zero0']}]){
    const text=exactJson(value),decoded=JSON.parse(text);assert(text.includes('-0'));
    if(typeof decoded==='number')assert(Object.is(decoded,-0));else {assert(Object.is(decoded.a,-0));assert(Object.is(decoded.nested[0],-0));assert.equal(decoded.text,value.text);}
  }
  assert.throws(()=>exactJson(undefined));const circular={};circular.self=circular;assert.throws(()=>exactJson(circular));
});
check('theme cache is transparent and cannot be poisoned by caller mutation',()=>{
  const colors={...themePresets[0].colors},first=themeColorProperties(colors),snapshot={...first};first['--av-tone-ink']='corrupt';
  assert.deepEqual(themeColorProperties(colors),snapshot);
  for(let n=0;n<40;n++)themeColorProperties({...colors,main:'#'+n.toString(16).padStart(6,'0')});
  assert.deepEqual(themeColorProperties(colors),snapshot);assert.throws(()=>themeColorProperties({...colors,main:'url(bad)'}));
});
check('toggle, extend, additive range, retained pivot and source ordering',()=>{
  const order=['a','b','c','d','e'];let state={keys:[],pivot:null};
  state=changeItemSelection(state,order,'b');assert.deepEqual(state,{keys:['b'],pivot:'b'});
  state=changeItemSelection(state,order,'d',true);assert.deepEqual(state.keys,['b','d']);
  state=changeItemSelection(state,order,'d',true);assert.deepEqual(state,{keys:['b'],pivot:'d'});
  state=changeItemSelection(state,order,'e',false,true);assert.deepEqual(state.keys,['d','e']);
  state=changeItemSelection(state,order,'b',true,true);assert.deepEqual(state.keys,['b','c','d','e']);
  assert.equal(changeItemSelection(state,order,'missing'),state);
});
function study(){const f=fixture();const root=f.parse(V.reportSurface({id:'experience',body:V.scatterPlot({id:'observations',title:'Duplicate labels',xAxis:'Exact input',yAxis:'Exact result',points:[{id:'a',label:'Same',x:-0,y:2},{id:'b',label:'Same',x:1,y:3},{id:'c',label:'Other',x:2,y:4}]})})).firstChild;f.d.body.appendChild(root);const registry=createTargetRegistry(root,'r1');return{...f,root,registry,figure:root.querySelector('[data-av-figure]')};}
check('selection respects native editors, exact inspector trigger and authored filter cleanup',()=>{
  const {d,root,registry,figure}=study(),mark=figure.querySelector('[data-av-inspect]'),scroll=figure.querySelector('.av-plot-scroll');
  const computed=d.defaultView.getComputedStyle;d.defaultView.getComputedStyle=node=>({...computed(node),filter:node===mark?'url("#author-filter")':'none'});
  mark.style.setProperty('--av-item-base-filter','older-property');const calls=[];
  const ui=mod('item-selection').attachItemSelection(root,[figure],{inspect:(...args)=>calls.push(args),review:()=>{},canReview:()=>true});
  figure.setAttribute('data-av-selection-mode','select');ui.refresh();
  assert(mark.style.getPropertyValue('--av-item-filter-chain').includes('author-filter'));
  const mouse={ctrlKey:false,metaKey:false,shiftKey:false};assert(ui.click(mouse,mark));const inspect=figure.querySelector('[data-av-selection-command="inspect"]');assert(ui.click(mouse,inspect));assert(calls.at(-1)[2]===figure.querySelector('[data-av-selection-menu]'),'Inspection returns to the reachable selection chip, not a hidden action in its panel');
  const native=append(scroll,'input');assert.equal(ui.keydown({key:'a',ctrlKey:true},native),false);assert.equal(ui.keydown({key:'ArrowRight'},native),false);
  assert.equal(figure.querySelectorAll('[data-av-item-selected]').length,1);ui.cleanup();
  assert.equal(mark.style.getPropertyValue('--av-item-base-filter'),'older-property');assert.equal(mark.style.getPropertyValue('--av-item-filter-chain'),'');assert.equal(figure.querySelector('.av-item-selection'),null);registry.cleanup();
});
check('multi-item anchors keep identity through order changes and never partially reattach',()=>{
  const {d,root,registry,figure}=study(),marks=Array.from(figure.querySelectorAll('[data-av-inspect]'));
  const anchor=registry.items(marks.slice(0,2));assert.equal(anchor.kind,'items');assert.equal(anchor.items.length,2);assert.notEqual(anchor.items[0].itemId,anchor.items[1].itemId);assert.equal(registry.resolve(anchor).status,'resolved');
  marks[0].parentNode.appendChild(marks[0]);assert.equal(registry.resolve(anchor).status,'resolved');
  const savedId=marks[1].getAttribute('data-av-inspect');marks[1].setAttribute('data-av-inspect','different');assert.notEqual(registry.resolve(anchor).status,'resolved');marks[1].setAttribute('data-av-inspect',savedId);
  const duplicate=marks[1].cloneNode(true);marks[1].parentNode.appendChild(duplicate);assert.equal(registry.resolve(anchor).status,'ambiguous');duplicate.remove();
  assert.throws(()=>validateAnchor({...anchor,items:[anchor.items[0],anchor.items[0]]}));
  registry.cleanup();
});
check('fresh resolution batch performs one document scan and detects later ID changes',()=>{
  const {d,root,registry,figure}=study(),anchor=registry.anchor(figure);let scans=0;const query=d.querySelectorAll.bind(d);
  d.querySelectorAll=selector=>{if(selector==='[id]')scans++;return query(selector);};
  assert(registry.resolveAll(Array(100).fill(anchor)).every(r=>r.status==='resolved'));assert.equal(scans,1);
  const dupe=append(d.body,'div',{id:anchor.target.id});assert.equal(registry.resolve(anchor).status,'ambiguous');dupe.remove();assert.equal(registry.resolve(anchor).status,'resolved');
  registry.cleanup();
});
check('group review, backup and handoff preserve exact values and literal feedback',()=>{
  const {root,registry,figure}=study(),base=registry.items(Array.from(figure.querySelectorAll('[data-av-inspect]')).slice(0,2));
  const anchor={...base,items:base.items.map((item,i)=>({...item,values:{value:i?0:-0,missing:null,unit:'s'}}))};
  const context={reportId:'experience',revision:'r1',targetIds:[...registry.targets.keys()],viewIds:[],journeyIds:[]};let book=S.emptyReaderNotebook(context);
  book=S.applyReaderDelta(book,{epoch:book.epoch,id:'d1',change:{type:'annotation',version:{id:'v1',annotationId:'n1',anchor,text:'```\n# Not an instruction\n<script>literal</script>',at:'2026-09-20T12:00:00Z',draft:false},observedIds:[]}},context);
  const raw=S.encodeReaderNotebook(book,context),read=S.decodeReaderNotebook(raw,context);assert(Object.is(read.review.versions[0].anchor.items[0].values.value,-0));
  const handoff=reviewHandoff(read,registry,'Original question','Actual report');assert(handoff.includes('"value":-0'));assert(handoff.includes('Selected item:'));assert(handoff.includes('````text'));assert(handoff.includes('<script>literal</script>'));registry.cleanup();
});
check('record reconciliation retains disclosures and selection while share excludes recovery bytes',()=>{
  const {d,root,registry,figure}=study(),context={reportId:'experience',revision:'r1',targetIds:[...registry.targets.keys()],viewIds:[],journeyIds:[]};let book=S.emptyReaderNotebook(context),n=0;
  const ui=attachContextReview(root,registry,{notebook:()=>book,change:change=>{book=S.applyReaderDelta(book,{epoch:book.epoch,id:'d'+(++n),change},context);return true;},reveal:()=>{},now:()=> '2026-09-20T12:00:00Z',id:()=> 'v'+(++n)});
  const action=(node,key)=>node.querySelector('[data-av-review-action="'+key+'"]');
  ui.click(action(figure,'new-note'));const editor=root.querySelector('.av-context-review'),field=editor.querySelector('textarea');field.value='Keep exact feedback';ui.input(field);ui.click(action(editor,'save'));
  ui.click(action(figure,'bookmark'));
  const notes=append(root,'ul'),bookmarks=append(root,'ul'),inclusions=append(root,'div');ui.render([notes],[bookmarks],[inclusions]);
  const card=notes.querySelector('[data-av-review-entry]'),original=card.querySelector('details');original.open=true;const edit=action(card,'edit');edit.focus();
  const mark=bookmarks.querySelector('[data-av-review-bookmark]');ui.render([notes],[bookmarks],[inclusions]);assert.equal(notes.querySelector('[data-av-review-entry]'),card);assert.equal(bookmarks.querySelector('[data-av-review-bookmark]'),mark);assert(original.open);assert.equal(d.activeElement,edit);
  const input=inclusions.querySelector('input');input.checked=false;ui.change(input);
  book={...book,originals:['PRIVATE RECOVERY'],reviewImports:['PRIVATE IMPORT']};const filtered=ui.exportNotebook(book);assert.equal(filtered.review.versions.length,0);assert.deepEqual(filtered.originals,[]);assert.deepEqual(filtered.reviewImports,[]);assert.equal(book.originals[0],'PRIVATE RECOVERY');
  ui.cleanup();registry.cleanup();assert.equal(d.listenerCount,0);
});
check('unanchorable passages never silently become bookmarks on another target',()=>{
  const {d,root,registry,figure}=study(),context={reportId:'experience',revision:'r1',targetIds:[...registry.targets.keys()],viewIds:[],journeyIds:[]};let book=S.emptyReaderNotebook(context),n=0;const messages=[];
  const ui=attachContextReview(root,registry,{notebook:()=>book,change:change=>{book=S.applyReaderDelta(book,{epoch:book.epoch,id:'d'+(++n),change},context);return true;},reveal:()=>{},notify:m=>messages.push(m),now:()=> '2026-09-20T12:00:00Z',id:()=> 'v'+(++n)});
  const mark=figure.querySelector('[data-av-inspect]');figure.setAttribute('data-av-selection-mode','text');mark.setAttribute('data-av-item-selected','');
  d.defaultView.getSelection=()=>({isCollapsed:false,rangeCount:0,anchorNode:mark,focusNode:mark});
  assert(ui.click(figure.querySelector('[data-av-review-action="bookmark"]')));assert.equal(book.review.bookmarks.length,0);assert.equal(messages[0].tone,'error');
  d.defaultView.getSelection=()=>({isCollapsed:true,rangeCount:0});assert(ui.click(figure.querySelector('[data-av-review-action="bookmark"]')));assert.equal(book.review.bookmarks[0].kind,'figure');
  ui.cleanup();registry.cleanup();
});
check('literal search separates status words and indexes hidden evidence but not controls',()=>{
  const {d,parse}=fixture(),root=parse(V.evidenceWorkspace({id:'search-study',title:'Question search',views:[{id:'one',label:'Overview',body:'<p>Literal &lt;script&gt; stays text <span class="av-status">failed</span>next</p>'},{id:'two',label:'Hidden',body:'<p>Hidden evidence needle</p><button>Never indexed secret control</button>'}]})).firstChild;d.body.appendChild(root);
  root.querySelector('[data-av-panel="two"]')?.setAttribute('hidden','');const entries=reportEntries(root);assert(entries.some(e=>e.text.includes('Hidden evidence needle')));assert(!entries.some(e=>e.text.includes('secret control')));assert(entries.some(e=>e.text.includes('failed next')));
});
check('grouped search caps each type, expands independently, uses safe text and cleans up',()=>{
  const {d,parse}=fixture(),root=parse(V.evidenceWorkspace({id:'search-study',title:'Needle question',views:[{id:'one',label:'Needle section',body:'<p>Needle evidence</p>'}]})).firstChild;d.body.appendChild(root);
  const holder=append(root,'div'),input=append(holder,'input'),results=append(root,'div');let activated=0;
  const notes=Array.from({length:25},(_,i)=>({kind:'notes',label:'Needle '+i,text:'<script>literal</script>',context:'Context',activate:()=>activated++}));
  const controller=attachReportSearch(root,input,results,{notes:()=>notes,reveal:()=>{},close:()=>{input.value='';}});input.value='needle';controller.update(input.value);
  let group=results.querySelector('[data-av-search-group="notes"]');assert.equal(group.querySelectorAll('[data-av-search-result]').length,3);assert(!results.querySelector('script'));send(Array.from(group.querySelectorAll('button')).find(b=>b.textContent.startsWith('Show ')),'click');group=results.querySelector('[data-av-search-group="notes"]');assert.equal(group.querySelectorAll('[data-av-search-result]').length,23);
  send(group.querySelector('[data-av-search-result]'),'click');assert.equal(activated,1);assert(results.hidden);controller.cleanup();assert.equal(d.listenerCount,0);
});
check('regex syntax parser admits JS matching flags without global-state flags or oversized code',()=>{
  assert.deepEqual(regexSpec('/a.+b/imsu'),{pattern:'a.+b',flags:'imsu'});assert.deepEqual(regexSpec('node.*'),{pattern:'node.*',flags:'iu'});
  for(const query of ['/a/g','/a/y','/a/ii','a'.repeat(2001)])assert.throws(()=>regexSpec(query));
});
check('source access validates custom values and failed source opening is an explicit result',()=>{
  const {d,parse}=fixture();let broken=false;const release=V.registerVisualAdapter('source-change',{bounds:()=>({width:200,height:100}),source:()=>{if(broken)throw Error('Source unavailable');return{language:'text',text:'original'};}});
  const figure=parse(V.visualFigure({title:'Source',adapter:'source-change',body:'<svg width="200" height="100"><text>Original</text></svg>'})).firstChild;d.body.appendChild(figure);const messages=[];
  const tools=mod('figure-tools').attachFigureTools(figure,()=>{},message=>messages.push(message));broken=true;assert(tools.click(figure.querySelector('[data-av-figure-action="source"]')));assert.equal(messages[0].tone,'error');assert.match(messages[0].text,/Source unavailable/);tools.cleanup();release();
});
console.log(`${checks} reader experience contracts passed (models, not native layout)`);
