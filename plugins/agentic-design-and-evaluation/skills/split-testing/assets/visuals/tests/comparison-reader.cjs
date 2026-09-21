// Exact compiled code, explicit DOM/geometry models. Native UI is checked separately.
const assert=require('node:assert/strict'),path=require('node:path');
const {fixture,V,send}=require('./parsed-dom-fixture.cjs');
const {comparisonWindow,attachComparisonReader}=require(path.join(process.argv[2],'comparison-reader.js'));
const {createTargetRegistry,reviewText}=require(path.join(process.argv[2],'review-targets.js'));
let assertions=0;const test=(name,fn)=>{fn();assertions++;console.log('ok '+name);};
test('window cardinality, source order, reference and bounds across empty and large sets',()=>{
 for(const n of [0,1,2,3,12,250])for(const capacity of [1,2,3,4])for(const offset of [-1,0,1,n-1,n+3])for(const pinned of [null,'r0','r5','absent']){
  const keys=Array.from({length:n},(_,i)=>'r'+i),result=comparisonWindow(keys,capacity,offset,pinned);
  assert(result.keys.length<=capacity);assert.equal(new Set(result.keys).size,result.keys.length);assert(result.keys.every(key=>keys.includes(key)));
  assert(result.offset>=0&&result.offset<=Math.max(0,result.remaining.length-1));
  if(pinned&&keys.includes(pinned)&&capacity>1)assert.equal(result.keys[0],pinned);
  const scrolling=result.keys.filter(key=>key!==pinned);assert(scrolling.every((key,i)=>!i||keys.indexOf(scrolling[i-1])<keys.indexOf(key)));
 }
 assert.deepEqual(comparisonWindow(['a','b','c'],1,1,'a',true).keys,['a']);
 assert.deepEqual(comparisonWindow(['a','b','c'],1,1,'a',false).keys,['c']);
 assert.equal(comparisonWindow(['a'],NaN,Infinity,null).keys[0],'a');
});
function create(){const f=fixture(),root=f.parse(V.reportSurface({id:'test-readers',body:V.nativeArtifactViewer({id:'records',title:'Exact records',artifacts:Array.from({length:12},(_,i)=>({label:i<2?'Repeated label':'Record '+i,mediaType:'text/plain',text:`id: ${i}\nExact ${i}: <untrusted> 日本語\n`+'retained text '.repeat(i+1)}))})})).firstChild;f.d.body.appendChild(root);const explorer=root.querySelector('[data-av-explorer]'),stage=root.querySelector('.av-deck-grid'),objects=stage.querySelectorAll('[data-av-object]');stage.clientWidth=960;return{...f,root,explorer,stage,objects};}
test('pinning and paging change presentation, never annotation grounds or original records',()=>{
 const {d,root,explorer,stage,objects}=create(),registry=createTargetRegistry(root,'v1'),anchor=registry.anchor(root),text=reviewText(root),order=[...objects],bodies=objects.map(object=>object.querySelector('.av-object-body'));
 const reader=attachComparisonReader(explorer,stage,objects);
 assert.equal(reviewText(root),text);assert.equal(registry.resolve(anchor).status,'resolved');
 for(const check of explorer.querySelectorAll('[data-av-compare]'))check.checked=true;reader.compare();assert.equal(objects.filter(object=>!object.hidden).length,3);
 send(objects[2].querySelector('[data-av-pin-record]'),'click');assert.equal(stage.children[0],objects[2]);assert.equal(registry.resolve(anchor).status,'resolved');assert.equal(reviewText(root),text);
 send(explorer.querySelector('[data-av-reader-next]'),'click');assert.equal(stage.children[0],objects[2]);assert.equal(objects.filter(object=>!object.hidden).length,3);assert.equal(registry.resolve(anchor).status,'resolved');
 send(explorer.querySelector('[data-av-reader-cards]'),'click');assert.equal(objects.filter(object=>!object.hidden).length,12);assert.equal(registry.resolve(anchor).status,'resolved');
 // Real evidence mutations remain visible through the live canonical order.
 const original=bodies[8].textContent;bodies[8].textContent='Changed evidence';assert.equal(registry.resolve(anchor).status,'changed');
 bodies[8].textContent=original; // This also removed markup, so no stronger assertion is made about structural identity.
 reader.cleanup();assert.deepEqual(stage.children,order);assert.equal(explorer.querySelector('.av-record-picker'),null);assert.equal(d.listenerCount,0);registry.cleanup();
});
test('reader revisiting, filtered selection, legacy commands and cleanup are independent',()=>{
 const {d,root,explorer,stage,objects}=create(),reader=attachComparisonReader(explorer,stage,objects);
 const checks=explorer.querySelectorAll('[data-av-compare]');checks[0].checked=checks[4].checked=checks[9].checked=true;reader.compare();
 assert.deepEqual(objects.filter(x=>!x.hidden).map(x=>x.getAttribute('data-av-object')),['artifact-0','artifact-4','artifact-9']);
 stage.clientWidth=280;reader.render();assert.equal(objects.filter(x=>!x.hidden).length,1);
 reader.reveal('artifact-9');assert.equal(objects[9].hidden,false);assert.equal(checks.filter(x=>x.checked).length,3,'Reveal a member keeps the chosen set');
 reader.reveal('artifact-8');assert.equal(objects[8].hidden,false);assert.equal(checks.filter(x=>x.checked).length,3,'Read another record without silently discarding the comparison');
 reader.reset();assert(checks.every(x=>!x.checked));assert.equal(objects.filter(x=>!x.hidden).length,1);
 send(explorer.querySelector('[data-av-read-compare]'),'click');const search=explorer.querySelector('[data-av-record-search]');search.value='Exact 11:';send(search,'input');send(explorer.querySelector('[data-av-records-all]'),'click');assert.equal(checks[11].checked,true);assert.equal(checks[10].checked,false);
 reader.cleanup();assert.equal(d.listenerCount,0);assert.equal(root.querySelector('[data-av-record-picker]'),null);
});
console.log(`${assertions} comparison reader contracts passed (explicit models)`);
