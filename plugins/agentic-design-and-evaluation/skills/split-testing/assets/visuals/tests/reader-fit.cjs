// Actual report markup/controllers plus explicit geometry, font and DOM models.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {fixture,V,append,send}=require('./parsed-dom-fixture.cjs');
const {click,pointer}=require('./viewport-fixture.cjs');
const examples=[
  ()=>V.distribution({title:'Sessions and qualified labels',axis:'Capture time',unit:'s',groups:[{id:'same-1',label:'Repeated label',observations:[{label:'Session 👩🏽‍🚀 with original qualification',value:3},{label:'Failed session',value:null,status:'failed'}]},{id:'same-2',label:'Repeated label',observations:[{label:'Another session',value:12}]}]}),
  ()=>V.pairedComparison({title:'Paired observations',axis:'Time',leftLabel:'Before',rightLabel:'After',pairs:[{label:'A complete and long qualification',left:0,right:9}]}),
  ()=>V.evidenceLineage({title:'Relationships with complete wording',nodes:[{id:'a',label:'Original source',kind:'observation'},{id:'b',label:'Conditional claim',kind:'claim'}],edges:[{id:'link',from:'a',to:'b',relation:'supports only under the original stated conditions'}]}),
  ()=>V.scatterPlot({title:'Complete and partial coordinates',xAxis:'Time',yAxis:'Effort',points:[{id:'a',label:'A',x:1,y:2},{id:'b',label:'B',x:8,y:6},{id:'c',label:'X only',x:10,y:null}]}),
];
for(const available of [160,180,185,200,280,420,900,1280]) for(const render of examples){
  const {d,parse}=fixture(); d.defaultView.CustomEvent=class{constructor(type,options={}){this.type=type;Object.assign(this,options);}};
  const frame=parse(render()).querySelector('.av-card');d.body.appendChild(frame);
  const source=frame.getAttribute('data-av-layout-input'), table=frame.querySelector('.av-data'), evidence=table.textContent;
  const before=frame.querySelectorAll('[data-av-plot]').map(plot=>({plot,controls:plot.querySelectorAll('[data-av-zoom-in],[data-av-zoom-out],[data-av-zoom-reset]')}));
  assert.equal(frame.querySelectorAll('[data-av-fit-width],[data-av-actual-size]').length,0,'The delivered chart offers only Reset, + and − for sizing');
  const expand=frame.querySelector('[data-av-focus]');assert.equal(expand.closest('.av-card-header'),frame.querySelector('.av-card-header'),'Expand shares the existing heading, never a reserved content row');
  for(const {plot,controls} of before){
    assert.equal(controls.length,3);
    const svg=plot.querySelector('[data-av-zoom-target]'),viewport=svg.parentElement,rows=plot.querySelector('[data-av-axis-layer="rows"]'),layout=plot.querySelector('.av-row-plot-layout');
    const visible=()=>!plot.closest('[hidden]');
    const rowWidth=()=>Number.parseFloat(plot.style.getPropertyValue('--av-axis-row-width'))||Number(rows?.getAttribute('width'))||0;
    if(rows){layout.clientWidth=available;Object.defineProperty(rows.parentElement,'clientWidth',{get:rowWidth});}
    Object.defineProperty(viewport,'clientWidth',{get:()=>visible()?Math.max(0,available-(rows?rowWidth():0)):0});
    Object.defineProperty(viewport,'clientHeight',{get:()=>Number.parseFloat(plot.style.getPropertyValue('--av-plot-fit-height'))||400});
    svg.getBoundingClientRect=()=>{const width=visible()?(Number.parseFloat(svg.style.getPropertyValue('width'))||Number(svg.getAttribute('width'))):0;return{x:0,y:0,left:0,top:0,width,height:width*Number(svg.getAttribute('height'))/Number(svg.getAttribute('width'))};};
    Object.defineProperty(viewport,'scrollWidth',{get:()=>Math.max(viewport.clientWidth,svg.getBoundingClientRect().width)});
    Object.defineProperty(viewport,'scrollHeight',{get:()=>Math.max(viewport.clientHeight,svg.getBoundingClientRect().height)});
  }
  const cleanup=V.enhanceVisuals(frame);
  for(const {plot,controls} of before){
    if(plot.closest('[hidden]'))continue;
    const svg=plot.querySelector('[data-av-zoom-target]'),viewport=svg.parentElement,rows=plot.querySelector('[data-av-axis-layer="rows"]');
    assert(Math.abs(viewport.scrollWidth-viewport.clientWidth)<1e-7,'Default fit has no horizontal overflow');assert.equal(viewport.scrollHeight,viewport.clientHeight,'Default fit retains every row without a nested vertical scrollbar');
    if(rows)assert(Number.parseFloat(rows.style.getPropertyValue('width'))<=rows.parentElement.clientWidth+.01,'Row identity column fits without sideways scrolling');
    const geometry=svg.getAttribute('viewBox'),reset=controls.find(c=>c.hasAttribute('data-av-zoom-reset')),plus=controls.find(c=>c.hasAttribute('data-av-zoom-in'));
    const event=click(plus);assert.equal(event.defaultPrevented,true,'Sizing buttons in the summary do not toggle the section');assert.equal(frame.open,true);assert.equal(plot.getAttribute('data-av-zoom'),'1.25');
    assert(viewport.scrollWidth>viewport.clientWidth);assert.equal(viewport.getAttribute('data-av-pan'),'ready');
    pointer(svg,'pointerdown');pointer(d,'pointermove',{clientX:-10000,clientY:-10000});pointer(d,'pointerup');assert(viewport.scrollLeft<=viewport.scrollWidth-viewport.clientWidth);
    click(reset);assert.equal(svg.getAttribute('viewBox'),geometry);assert.equal(viewport.scrollLeft,0);assert.equal(viewport.scrollTop,0);assert(Math.abs(viewport.scrollWidth-viewport.clientWidth)<1e-7);
  }
  assert.equal(frame.querySelector('.av-frame-content').querySelector('.av-frame-tools'),null,'No otherwise empty row is reserved for Expand');
  const toggle=frame.querySelector('[data-av-view-switch]');assert(toggle);click(toggle);assert.equal(frame.open,true);click(toggle);assert.equal(frame.open,true);
  assert.equal(frame.querySelector('.av-data'),table);assert.equal(table.textContent,evidence);assert.equal(frame.getAttribute('data-av-layout-input'),source);
  cleanup();assert.equal(d.listenerCount,0);
}
for(const initiallyOpen of [true,false]) {
  const {d,parse}=fixture();d.defaultView.CustomEvent=class{constructor(type,options={}){this.type=type;Object.assign(this,options);}};
  const title='Observed timing',frame=parse(V.pairedComparison({title,open:initiallyOpen,axis:'Seconds',leftLabel:'A',rightLabel:'B',pairs:[{label:'Original case',left:1,right:4}]})).querySelector('.av-card');d.body.appendChild(frame);
  const plot=frame.querySelector('[data-av-plot]'),svg=plot.querySelector('[data-av-zoom-target]'),viewport=svg.parentElement,expand=frame.querySelector('[data-av-focus]'),plus=frame.querySelector('[data-av-zoom-in]'),reset=frame.querySelector('[data-av-zoom-reset]');
  const controls=frame.querySelector('.av-frame-tools'),header=frame.querySelector('.av-card-header'),before=header.childNodes.slice();
  Object.defineProperty(viewport,'clientWidth',{get:()=>frame.open?480:0});viewport.clientHeight=400;
  svg.getBoundingClientRect=()=>({x:0,y:0,left:0,top:0,width:Number.parseFloat(svg.style.getPropertyValue('width'))||Number(svg.getAttribute('width')),height:400});
  Object.defineProperty(viewport,'scrollWidth',{get:()=>Math.max(viewport.clientWidth,svg.getBoundingClientRect().width)});viewport.scrollHeight=400;
  const cleanup=V.enhanceVisuals(frame);click(expand);
  const dialog=d.querySelector('dialog');assert(dialog.open);assert.equal(frame.open,true,'Expanding a closed card exposes its content');
  assert.equal(dialog.querySelector('.av-dialog-title').textContent,title,'The title excludes controls and live status');
  assert.equal(controls.closest('.av-card-header'),null,'Expanded actions escape the suppressed original heading');
  assert.equal(controls.closest('.av-dialog-header'),dialog.querySelector('.av-dialog-header'));
  click(plus);assert.equal(plot.getAttribute('data-av-zoom'),'1.25');click(reset);assert.equal(plot.getAttribute('data-av-zoom'),'1');
  const data=controls.querySelector('[data-av-view-switch]');click(data);assert.equal(plot.hidden,true);click(data);assert.equal(plot.hidden,false,'Moved Data switch still returns to the chart');
  click(dialog.querySelector('[data-av-close-focus]'));assert.equal(frame.open,initiallyOpen);assert.equal(controls.parentNode,header);assert.equal(frame.parentNode,d.body);
  cleanup();assert.deepEqual(header.childNodes,before);
}
// Temporary inspection does not participate in the background's solo group.
for(const targetFirst of [true,false]) {
  const {d,parse}=fixture();
  const target=V.reportSection({id:'temporary-target',title:'Inspect the closed section',open:false,body:V.reportSection({id:'nested-one',title:'Nested one',body:'<p>One</p>'})+V.reportSection({id:'nested-two',title:'Nested two',body:'<p>Two</p>'})});
  const peer=V.reportSection({id:'background-peer',title:'Current reading section',body:'<p>Original reading position</p>'});
  const root=parse(V.reportSurface({id:'solo-inspection',sections:'solo',body:V.appearanceSettings({id:'display'})+(targetFirst?target+peer:peer+target)})).querySelector('.av-surface');d.body.appendChild(root);
  const frame=root.querySelector('[id="temporary-target"]'),background=root.querySelector('[id="background-peer"]'),control=frame.querySelector('[data-av-focus]');
  const cleanup=V.enhanceVisuals(root);assert(background.open);assert(!frame.open);click(control);
  const dialog=root.querySelector('dialog');assert(dialog.open);assert(frame.open,'Mirroring preferences must not close the temporarily expanded card');assert(background.open,'Inspecting a closed card must not close the background peer');
  const nested1=frame.querySelector('[id="nested-one"]'),nested2=frame.querySelector('[id="nested-two"]');nested2.open=true;send(nested2,'toggle',{bubbles:false});assert(!nested1.open);assert(nested2.open);assert(frame.open);
  const dark=root.querySelector('[data-av-setting="theme"][value="dark"]');dark.checked=true;send(dark,'change');assert(frame.open);assert(background.open,'Reapplying preferences preserves both independently owned states');
  click(dialog.querySelector('[data-av-close-focus]'));assert(!frame.open);assert(background.open);assert.equal(control.closest('.av-card-header'),frame.querySelector('.av-card-header'));cleanup();
}
console.log('reader fit: real renderer/control compositions pass at eight widths, with open/closed expanded frames, preserving complete evidence (explicit geometry and DOM models only)');
