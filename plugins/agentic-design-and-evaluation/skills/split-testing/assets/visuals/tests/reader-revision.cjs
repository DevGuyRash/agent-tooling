/** Regression contracts for this revision. These are explicit models, not a browser. */
const assert = require('node:assert/strict');
const path = require('node:path');
const crypto = require('node:crypto');
const compiled = process.argv[2];
const { fixture, V, append, send } = require('./parsed-dom-fixture.cjs');
const { click } = require('./viewport-fixture.cjs');
const { fingerprint } = require(path.join(compiled, 'identity.js'));
const { categoryStyle, createChartContext } = require(path.join(compiled, 'categories.js'));
const R = require(path.join(compiled, 'reader-state.js'));
const { createOwnedStore } = require(path.join(compiled, 'reader-storage.js'));
const { reviewHandoff } = require(path.join(compiled, 'review-export.js'));
const { createTargetRegistry } = require(path.join(compiled, 'review-targets.js'));
const { attachCommandBar } = require(path.join(compiled, 'command-bar.js'));
const { attachContextReview } = require(path.join(compiled, 'context-review.js'));
const { applyReview } = require(path.join(compiled, 'review-state.js'));

async function main() {
  for (const text of ['', 'Original e\u0301 / 日本語 / 👩🏽‍🚀', '\ud800', 'a'.repeat(2048)]) {
    assert.equal(fingerprint(text), 'sha256-utf16le:' + crypto.createHash('sha256').update(Buffer.from(text, 'utf16le')).digest('hex'));
  }
  // The retained layout recipe must not turn a supplied -0 into +0 or replace
  // an authored string that happens to resemble the encoder's temporary marker.
  {
    const { parse } = fixture();
    const title = '\u0000av-negative-zero';
    const card = parse(V.pairedComparison({title,axis:'Residual',leftLabel:'Before',rightLabel:'After',pairs:[{label:'Run',left:-0,right:0}]})).firstChild;
    const recipe = JSON.parse(card.getAttribute('data-av-layout-input'));
    assert(Object.is(recipe.pairs[0].left, -0)); assert(Object.is(recipe.pairs[0].right, 0)); assert.equal(recipe.title, title);
  }
  {
    const {parse}=fixture();
    const labels=['Bench run','Bench run','Record 1 · Bench run'];
    const root=parse(V.nativeArtifactViewer({title:'Records',artifacts:labels.map(label=>({label,mediaType:'text/plain',text:'Original '+label}))})).firstChild;
    const names=[...root.querySelectorAll('[data-av-object]')].map(n=>n.querySelector('summary').textContent);
    assert.equal(new Set(names).size,3);assert.equal(names[0],'Record 1 · Bench run');assert.equal(names[2],'Record 3 · Record 1 · Bench run');
    assert.equal(root.querySelector('[data-av-object="artifact-0"]').querySelector('pre').textContent,'Original Bench run');
    assert(root.querySelector('[data-av-compare="artifact-0"]').parentElement.textContent.includes(names[0]));
  }
  // Owned contexts are immutable/indexed. Ad hoc mutable contexts are not cached.
  {
    const categories = Array.from({length:150},(_,i)=>({id:'id-'+i,label:'Repeated label'}));
    const frozen = createChartContext({categories});
    for (const category of categories) assert.deepEqual(categoryStyle(category.id, frozen), categoryStyle(category.id, {categories: categories.slice().reverse()}));
    const mutable = {categories:[{id:'a',label:'A',style:{shape:'circle'}}]};
    assert.equal(categoryStyle('a',mutable).shape,'circle'); mutable.categories[0].style.shape='square';
    assert.equal(categoryStyle('a',mutable).shape,'square'); assert(Object.isFrozen(frozen.categories));
  }
  const context = {reportId:'report',revision:'r2',targetIds:['report','target'],viewIds:[],journeyIds:[],activityLimit:20};
  const older = {...context,revision:'r1'};
  const previous = R.emptyReaderNotebook(older);
  const note = R.applyReaderDelta(previous,{epoch:previous.epoch,id:'first',baseNoteIds:[],change:{type:'note',targetId:'target',text:'Original older note',at:'2026-09-19T12:00:00Z'}},older);
  for (const owner of [
    {kind:'preferences',reportId:'report',revision:'r1'},
    {kind:'notebook',reportId:'other',revision:'r1'},
    {kind:'notebook',reportId:'report',revision:'unrelated'},
  ]) assert.throws(()=>R.importReaderReview(JSON.stringify({version:1,owner,value:note}),context));
  const raw = JSON.stringify({version:1,owner:{kind:'notebook',reportId:'report',revision:'r1'},value:note});
  const migrated = R.importReaderReview(raw,context);
  assert(migrated.originals.includes(raw)); assert.equal(migrated.review.versions[0].anchor.target.revision,'r1');
  assert.equal(migrated.review.versions[0].text,'Original older note');
  assert.throws(()=>R.importReaderReview(JSON.stringify({version:999,owner:{kind:'notebook',reportId:'report',revision:'r1'},value:note}),context));
  {
    const {d} = fixture(),scope=append(d.body,'section',{id:'report'});
    const unassigned=append(scope,'section',{class:'av-card'});append(unassigned,'h2',{},'No ID yet');
    const one=append(scope,'section',{id:'duplicate',class:'av-card'}),two=append(scope,'section',{id:'duplicate',class:'av-card'});
    assert.throws(()=>createTargetRegistry(scope,'r2'),/unique/);assert.equal(unassigned.id,'');
    two.id='different';const registry=createTargetRegistry(scope,'r2');
    const anchor=registry.anchor(one);one.id='changed';assert.equal(registry.resolve(anchor).status,'missing');
    registry.cleanup();assert.equal(unassigned.id,'');
  }
  {
    const {d,parse}=fixture();
    const root=parse(V.reportSurface({id:'owner',body:V.storyPanel({title:'Retained evidence',paragraphs:['Exact text.']})})).firstChild;d.body.appendChild(root);
    const card=root.querySelector('.av-card'),cleanup=V.enhanceVisuals(root);
    assert.equal(V.enhanceVisuals(root),cleanup);assert.throws(()=>V.enhanceVisuals(card),/already belongs/);
    cleanup();const childCleanup=V.enhanceVisuals(card);assert.throws(()=>V.enhanceVisuals(root),/independently enhanced/);childCleanup();
    V.enhanceVisuals(root)();assert.equal(root.querySelectorAll('.av-command-bar').length,0);
  }
  {
    const {d}=fixture(),scope=append(d.body,'section',{id:'report',class:'av-surface'});append(scope,'p',{},'Evidence without an authored heading.');
    const registry=createTargetRegistry(scope,'r2'),before=registry.anchor(scope);const editor=append(scope,'aside',{'data-av-review-ui':''});append(editor,'h3',{},'Your annotation');
    assert.equal(registry.anchor(scope).target.label,before.target.label);assert.equal(registry.resolve(before).status,'resolved');registry.cleanup();
  }
  {
    const {d}=fixture(),host=append(d.body,'div');host.clientWidth=80;
    const button=append(host,'button',{},'Original');const bar=attachCommandBar(host,'Actions');bar.add(button,{label:'Original',menuOnly:true});
    assert.equal(d.listenerCount,0,'Closed command bars add no document listeners');
    const menu=host.querySelector('.av-command-overflow');menu.open=true;send(menu,'toggle',{bubbles:false});
    assert.equal(d.listenerCount,3);send(d.body,'pointerdown');assert.equal(menu.open,false);assert.equal(d.listenerCount,0);bar.cleanup();
  }
  // The notebook's primary action uses the same anchored-review controller as
  // contextual actions. Legacy records remain readable without becoming the default.
  {
    const {d,parse}=fixture();const root=parse(V.evidenceWorkspace({id:'report',title:'Question',notebook:{revision:'r2'},views:[{id:'one',label:'Evidence',body:V.storyPanel({id:'target',title:'Finding',paragraphs:['Exact source.']})}]})).firstChild;d.body.appendChild(root);
    const cleanup=V.enhanceVisuals(root),target=root.querySelector('[data-av-notebook-target]');assert.equal(target.querySelector('option').textContent,'Question');assert([...target.querySelectorAll('option')].some(n=>n.textContent==='Evidence'));target.value='target';send(target,'change');
    click(root.querySelector('[data-av-notebook-action="new-annotation"]'));
    const editor=root.querySelector('.av-context-review'),textarea=editor.querySelector('textarea');textarea.value='Draft survives Escape';send(textarea,'input');send(textarea,'keydown',{key:'Escape'});
    assert(editor.hidden);assert(root.querySelector('[data-av-notebook-notes]').textContent.includes('Draft survives Escape'));
    click(root.querySelector('[data-av-notebook-action="bookmark-target"]'));assert(root.querySelector('[data-av-notebook-bookmarks]').textContent.includes('Finding'));
    cleanup();const again=V.enhanceVisuals(root);assert(root.querySelector('[data-av-notebook-notes]').textContent.includes('Draft survives Escape'));again();
  }
  // A rejected in-session edit must not be hidden or overwritten by switching targets.
  {
    const {d}=fixture(),scope=append(d.body,'section',{id:'report'}),a=append(scope,'section',{id:'target',class:'av-card'}),b=append(scope,'section',{id:'other',class:'av-card'});append(a,'h2',{},'A');append(b,'h2',{},'B');
    const registry=createTargetRegistry(scope,'r2');let notebook=R.emptyReaderNotebook(context),accept=false,n=0;
    const ui=attachContextReview(scope,registry,{notebook:()=>notebook,change:change=>{if(!accept)return false;notebook={...notebook,review:applyReview(notebook.review,change)};return true;},reveal(){},now:()=> '2026-09-19T12:00:00Z',id:()=>String(++n)});
    const trigger=append(scope,'button');ui.open(registry.anchor(a),trigger);const editor=scope.querySelector('.av-context-review'),textarea=editor.querySelector('textarea');textarea.value='Do not lose me';ui.input(textarea);send(textarea,'keydown',{key:'Escape'});assert(!editor.hidden);
    ui.open(registry.anchor(b),trigger);assert.equal(textarea.value,'Do not lose me');accept=true;send(textarea,'keydown',{key:'Escape'});assert(editor.hidden);assert.equal(notebook.review.versions[0].anchor.target.id,'target');ui.cleanup();registry.cleanup();
  }
  {
    const {d}=fixture(),scope=append(d.body,'section',{id:'report'}),target=append(scope,'section',{id:'target',class:'av-card'});append(target,'h2',{},'Untrusted <img src=x>');append(target,'p',{},'Original source');
    const registry=createTargetRegistry(scope,'r2'),anchor=registry.anchor(target),text='`````\n# Spoofed heading\n<img src=x onerror=run()>\nOriginal e\u0301';
    const notebook={...R.emptyReaderNotebook(context),review:{bookmarks:[anchor],versions:[{id:'v1',annotationId:'a1',anchor,text,at:'2026-09-19T12:00:00Z',draft:false}]}};
    const handoff=reviewHandoff(notebook,registry,text,text);assert(handoff.includes(text));
    let fence=null;for(const line of handoff.split('\n')) {if(!fence&&/^`{3,}text$/.test(line)){fence=line.slice(0,-4);continue;}if(line===fence){fence=null;continue;}if(!fence)assert(!line.includes('<img')&&!line.includes('Spoofed heading'));}assert.equal(fence,null);
    registry.cleanup();
  }
  // Force only the transaction watchdog, not a real fifteen-second wait.
  {
    const originalSet=global.setTimeout,originalClear=global.clearTimeout;let expire,getRequest,aborted=false,changed=false;
    const fakeTimer={testTimer:true};
    global.setTimeout=(fn,ms,...args)=>ms===15000?(expire=fn,fakeTimer):originalSet(fn,ms,...args);
    global.clearTimeout=id=>{if(id!==fakeTimer)originalClear(id);};
    try {
      const tx={objectStore(){return{get(){return getRequest={};},put(){throw Error('Late write');}};},abort(){aborted=true;this.onabort?.();}};
      const database={objectStoreNames:{contains:()=>true},transaction:()=>tx,close(){}};
      const win={indexedDB:{open(){const req={};queueMicrotask(()=>{req.result=database;req.onsuccess();});return req;}},localStorage:{getItem:()=>null}};
      const store=createOwnedStore(win,'timeout',{kind:'notebook',reportId:'report',revision:'r2'});
      const pending=store.update(()=>{changed=true;return {};});await new Promise(resolve=>setImmediate(resolve));assert(expire);expire();const result=await pending;
      assert.equal(result.status,'unavailable');assert(result.message.includes('not been confirmed'));assert(aborted);getRequest.onsuccess();assert(!changed);store.close();
    } finally {global.setTimeout=originalSet;global.clearTimeout=originalClear;}
  }
  console.log('reader revision contracts passed: exact numbers, identity, ownership, migration, timeout, literal handoff, active-only menus, shared notes and protected drafts');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
