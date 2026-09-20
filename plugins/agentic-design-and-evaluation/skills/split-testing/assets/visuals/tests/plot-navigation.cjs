// Viewport contracts with explicit DOM/geometry models; native CSS and gestures remain unverified.
const assert = require('node:assert/strict'), path = require('node:path');
const { attachPlots } = require(path.join(process.argv[2], 'plot-navigation.js'));
const { documentFixture, fixture, pointer, append, send, click } = require('./viewport-fixture.cjs');
const passed = [];
function check(name, body) { body(); passed.push(name); }
function near(actual, expected) { assert(Math.abs(actual - expected) < 1e-7, `${actual} != ${expected}`); }

check('initial and reset fit the entire chart; zoom is relative to that fit', () => {
  for (const width of [240, 480, 1080]) {
    const {document,observers} = documentFixture({observer:true}), root=append(document.body,'main');
    const a=fixture(document,root,{viewportWidth:width,responsive:true,minimumWidth:760,autoHeight:true}), original=a.svg.getAttribute('style'), api=attachPlots(root);
    near(a.rect().width,width); assert(a.rect().height<=a.viewport.clientHeight);
    assert.equal(a.viewport.getAttribute('data-av-pan'),null); assert.equal(a.minus.disabled,true); assert.equal(a.reset.disabled,true);
    assert.equal(a.plot.getAttribute('data-av-zoom'),'1'); assert.match(a.plot.querySelector('[data-av-zoom-status]').textContent,/100% zoom/);
    api.click(a.plus); near(a.rect().width,width*1.25); assert.equal(a.viewport.getAttribute('data-av-pan'),'ready');
    a.viewport.scrollLeft=20; a.viewport.scrollTop=10; send(a.viewport,'scroll');
    a.viewport.clientWidth=width+80; observers[0].trigger(); near(a.rect().width,(width+80)*1.25);
    api.click(a.reset); near(a.rect().width,width+80); assert.equal(a.viewport.scrollLeft,0); assert.equal(a.viewport.scrollTop,0); assert.equal(a.viewport.getAttribute('data-av-pan'),null);
    for(let i=0;i<30;i++)api.click(a.plus); assert(a.plus.disabled); assert(Number(a.plot.getAttribute('data-av-zoom'))>1);
    for(let i=0;i<30;i++)api.click(a.minus); near(a.rect().width,width+80); assert(a.minus.disabled);
    api.cleanup(); assert.equal(a.svg.getAttribute('style'),original); assert(observers.every(o=>o.disconnected));
  }
});

check('zoomed drag is bounded and distinguishes clicks, pen, touch and keyboard', () => {
  const {document}=documentFixture(), root=append(document.body,'main');
  const a=fixture(document,root,{autoHeight:true}), b=fixture(document,root,{autoHeight:true}), api=attachPlots(root);
  let activations=0; const inspect=()=>activations++; root.addEventListener('click',inspect);
  pointer(a.mark,'pointerdown'); pointer(document,'pointermove',{clientX:20}); pointer(document,'pointerup'); assert.equal(a.viewport.scrollLeft,0);
  for(let i=0;i<4;i++)api.click(a.plus);
  a.viewport.scrollLeft=0;a.viewport.scrollTop=0;send(a.viewport,'scroll');
  pointer(a.mark,'pointerdown'); pointer(document,'pointermove',{clientX:98}); pointer(document,'pointerup'); click(a.mark,{detail:1}); assert.equal(activations,1); assert.equal(a.captured.length,0);
  pointer(a.mark,'pointerdown'); pointer(document,'pointermove',{clientX:50,clientY:70});
  assert.equal(a.viewport.scrollLeft,50); assert.equal(a.viewport.scrollTop,30); assert(a.viewport.hasAttribute('data-av-dragging')); assert.deepEqual(a.captured,[7]); assert.equal(b.viewport.scrollLeft,0);
  pointer(document,'pointermove',{clientX:-10000,clientY:-10000});
  assert.equal(a.viewport.scrollLeft,a.viewport.scrollWidth-a.viewport.clientWidth); assert.equal(a.viewport.scrollTop,a.viewport.scrollHeight-a.viewport.clientHeight);
  pointer(document,'pointerup'); assert.equal(click(a.mark,{detail:1}).defaultPrevented,true); assert.equal(activations,1);
  pointer(a.mark,'pointerdown'); pointer(document,'pointermove',{clientX:10000,clientY:10000}); pointer(document,'pointercancel'); assert.equal(a.viewport.scrollLeft,0); assert.equal(a.viewport.scrollTop,0);
  assert.equal(click(a.mark,{detail:0}).defaultPrevented,false);
  pointer(a.mark,'pointerdown',{pointerType:'pen'}); pointer(document,'pointermove',{clientX:50,pointerType:'pen'}); pointer(document,'pointerup',{pointerType:'pen'}); assert.equal(click(a.mark,{detail:0,pointerType:'pen'}).defaultPrevented,true);
  const left=a.viewport.scrollLeft;
  for(const extra of [{pointerType:'touch'},{button:2},{isPrimary:false}]){pointer(a.mark,'pointerdown',extra);pointer(document,'pointermove',{clientX:-999,...extra});pointer(document,'pointerup',extra);assert.equal(a.viewport.scrollLeft,left);}
  const editor=append(a.viewport,'input');pointer(editor,'pointerdown');pointer(document,'pointermove',{clientX:-999});pointer(document,'pointerup');assert.equal(a.viewport.scrollLeft,left);
  assert.equal(send(a.viewport,'keydown',{key:'ArrowRight'}).defaultPrevented,false,'Native keyboard panning remains available');
  pointer(a.mark,'pointerdown');pointer(document,'pointermove',{clientX:50});send(document.defaultView,'blur');assert(!a.viewport.hasAttribute('data-av-dragging'));
  api.click(a.reset);assert.equal(a.viewport.scrollLeft,0);assert.equal(a.viewport.scrollTop,0);assert.equal(a.viewport.getAttribute('data-av-pan'),null);
  root.removeEventListener('click',inspect);api.cleanup();assert.equal(document.listenerCount,0);assert.equal(document.defaultView.listenerCount,0);assert.equal(a.viewport.listenerCount,0);
});

check('row identities fit once and stay readable while the observations zoom and pan', () => {
  const {document,observers}=documentFixture({events:true,observer:true}),root=append(document.body,'main');
  const a=fixture(document,root,{x:185,width:715,height:1800,layers:true,coupledRows:true,availableWidth:540,autoHeight:true});
  const text=[a.svg.textContent,a.rows.textContent,a.xAxis.textContent], source=[a.svg.getAttribute('viewBox'),a.rows.getAttribute('viewBox')];
  const requests=[];root.addEventListener('av-layout-request',e=>requests.push(e.detail));const api=attachPlots(root);
  const labelWidth=Number.parseFloat(a.rows.style.getPropertyValue('width'));near(a.rect().width+a.rows.parentElement.clientWidth,a.layout.clientWidth);assert.equal(a.viewport.getAttribute('data-av-pan'),null);
  const count=requests.length;for(let i=0;i<8;i++)observers[0].trigger();assert.equal(requests.length,count,'Settled geometry must not trigger an endless refinement loop');
  for(let i=0;i<4;i++)api.click(a.plus);
  near(Number.parseFloat(a.rows.style.getPropertyValue('width')),labelWidth);near(a.rows.parentElement.clientWidth,labelWidth);assert(a.viewport.clientWidth>0);
  near(Number.parseFloat(a.xAxis.style.getPropertyValue('width')),a.rect().width);
  const row=a.rows.querySelector('[data-av-row-center]'), transform=row.getAttribute('transform');
  const inverse=Number(transform.match(/scale\(1 ([^)]+)\)/)[1]); const screenScale=a.rect().height/Number(a.svg.getAttribute('height'));
  near(inverse*screenScale,labelWidth/Number(a.rows.getAttribute('width')),'Rows retain the fitted text scale');
  a.viewport.scrollLeft=100;a.viewport.scrollTop=200;send(a.viewport,'scroll');assert.equal(a.xAxis.style.getPropertyValue('transform'),'translateX(-100px)');assert.equal(a.rows.style.getPropertyValue('transform'),'translateY(-200px)');
  a.layout.clientWidth=900;observers[0].trigger();assert(a.viewport.clientWidth>0);near(a.rect().width,a.viewport.clientWidth*2);
  api.click(a.reset);near(a.rect().width+a.rows.parentElement.clientWidth,900);assert.equal(a.viewport.scrollTop,0);assert.equal(a.viewport.getAttribute('data-av-pan'),null);
  assert.deepEqual([a.svg.textContent,a.rows.textContent,a.xAxis.textContent],text);assert.deepEqual([a.svg.getAttribute('viewBox'),a.rows.getAttribute('viewBox')],source);
  api.cleanup();assert.equal(a.rows.getAttribute('preserveAspectRatio'),null);assert.equal(row.getAttribute('transform'),null);assert.equal(a.rows.getAttribute('style'),null);
});

check('refinement receives fitting width while zoom and selection survive font changes', () => {
  const {document}=documentFixture({events:true}),root=append(document.body,'main'),a=fixture(document,root,{autoHeight:true});
  const requests=[];a.plot.addEventListener('av-layout-request',event=>requests.push({...event.detail}));
  const api=attachPlots(root);api.click(a.plus);const zoom=a.rect().width;
  a.mark.setAttribute('aria-pressed','true');a.mark.classList.add('av-selected');a.mark.focus();
  append(document.body,'dialog').appendChild(a.plot);send(a.plot,'av-layout-invalidated');
  near(a.rect().width,zoom);assert.equal(requests.at(-1).mode,'fit');assert.equal(requests.at(-1).width,a.viewport.clientWidth);
  assert.equal(a.mark.parentNode,a.svg);assert.equal(document.activeElement,a.mark);assert.equal(a.mark.getAttribute('aria-pressed'),'true');
  const geometry=a.svg.getAttribute('viewBox');a.viewport.clientWidth=0;api.refresh();assert.equal(a.svg.getAttribute('viewBox'),geometry);
  a.viewport.clientWidth=480;api.refresh();near(a.rect().width,480*1.25);api.click(a.reset);near(a.rect().width,480);api.cleanup();
});

check('relocated toolbar ownership and independent plots survive enhancement cleanup', () => {
  const {document}=documentFixture(),root=append(document.body,'main'),outer=append(root,'section',{class:'av-card'}),inner=append(outer,'section',{class:'av-card'});
  const a=fixture(document,outer,{autoHeight:true}),b=fixture(document,inner,{autoHeight:true}),api=attachPlots(root);
  const bar=append(outer,'header');bar.appendChild(a.toolbar);api.click(a.plus);near(a.rect().width,a.viewport.clientWidth*1.25);near(b.rect().width,b.viewport.clientWidth);
  append(document.body,'dialog').appendChild(outer);api.click(b.plus);near(b.rect().width,b.viewport.clientWidth*1.25);api.click(a.reset);near(a.rect().width,a.viewport.clientWidth);
  a.svg.style.setProperty('color','red');a.plot.style.setProperty('--author-choice','retained');api.click(a.plus);pointer(a.mark,'pointerdown');pointer(document,'pointermove',{clientX:30});
  api.cleanup();api.cleanup();assert.equal(a.svg.style.getPropertyValue('color'),'red');assert.equal(a.svg.style.getPropertyValue('width'),'');assert.equal(a.plot.style.getPropertyValue('--author-choice'),'retained');assert.equal(a.plot.style.getPropertyValue('--av-plot-fit-height'),'');assert.equal(a.viewport.scrollLeft,0);assert.equal(a.viewport.scrollTop,0);assert(a.released.includes(7));assert.equal(document.listenerCount,0);assert.equal(a.viewport.listenerCount,0);assert.equal(api.click(a.plus),false);
});
console.log('plot navigation source contracts passed: '+passed.join('; '));
