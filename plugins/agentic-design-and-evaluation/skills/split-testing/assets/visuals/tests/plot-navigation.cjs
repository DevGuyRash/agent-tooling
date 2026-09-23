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

check('fit height includes the viewport frame instead of creating phantom pan', () => {
  const {document}=documentFixture(),root=append(document.body,'main'),a=fixture(document,root,{width:400,height:200,viewportWidth:400,viewportHeight:198});
  let fallback=198;Object.defineProperty(a.viewport,'clientHeight',{configurable:true,get:()=>{const fitted=Number.parseFloat(a.plot.style.getPropertyValue('--av-plot-fit-height'));return fitted>0?Math.max(0,fitted-2):fallback;},set:value=>{fallback=value;}});
  a.viewport.getBoundingClientRect=()=>({x:0,y:0,left:0,top:0,right:400,bottom:a.viewport.clientHeight+2,width:400,height:a.viewport.clientHeight+2});
  const api=attachPlots(root);assert.equal(a.plot.style.getPropertyValue('--av-plot-fit-height'),'202px');near(a.viewport.clientHeight,200);near(a.viewport.scrollHeight,200);assert.equal(a.viewport.getAttribute('data-av-pan'),null);assert.equal(a.viewport.getAttribute('title'),'Drawing fits. Zoom in to pan.');
  api.click(a.plus);assert(a.viewport.scrollHeight>a.viewport.clientHeight);assert.equal(a.viewport.getAttribute('data-av-pan'),'ready');assert.equal(a.viewport.getAttribute('title'),'Drag, wheel, or use arrow keys to pan.');api.click(a.reset);assert.equal(a.viewport.getAttribute('data-av-pan'),null);api.cleanup();
});

check('expanded fit reserves the viewport frame inside the declared height', () => {
  const {document}=documentFixture(),root=append(document.body,'main'),figure=append(root,'figure',{'data-av-expanded-figure':'','data-av-fit-height':'200','data-av-fit-policy':'natural'}),a=fixture(document,figure,{width:400,height:200,viewportWidth:500,viewportHeight:198});
  let fallback=198;Object.defineProperty(a.viewport,'clientHeight',{configurable:true,get:()=>{const fitted=Number.parseFloat(a.plot.style.getPropertyValue('--av-plot-fit-height'));return fitted>0?Math.max(0,fitted-2):fallback;},set:value=>{fallback=value;}});a.viewport.getBoundingClientRect=()=>({x:0,y:0,left:0,top:0,right:500,bottom:a.viewport.clientHeight+2,width:500,height:a.viewport.clientHeight+2});
  const api=attachPlots(root);near(a.rect().width,396);near(a.rect().height,198);near(a.viewport.clientHeight,198);near(a.viewport.scrollHeight,198);assert.equal(a.viewport.getAttribute('data-av-pan'),null);api.cleanup();
});

check('natural fit preserves intrinsic readability while shrinking, zooming and resetting', () => {
  const {document,observers}=documentFixture({observer:true}),root=append(document.body,'main'),figure=append(root,'figure',{'data-av-fit-policy':'natural'});
  const a=fixture(document,figure,{width:300,height:200,viewportWidth:1000,autoHeight:true}),api=attachPlots(root);
  near(a.rect().width,300);assert.equal(a.viewport.getAttribute('data-av-pan'),null);
  api.click(a.plus);near(a.rect().width,375);
  api.click(a.reset);near(a.rect().width,300);
  a.viewport.clientWidth=200;observers[0].trigger();near(a.rect().width,200);
  api.click(a.plus);near(a.rect().width,250);assert.equal(a.viewport.getAttribute('data-av-pan'),'ready');
  api.click(a.reset);near(a.rect().width,200);assert.equal(a.viewport.scrollLeft,0);
  figure.setAttribute('data-av-fit-policy','width');a.viewport.clientWidth=1000;observers[0].trigger();near(a.rect().width,1000);
  api.cleanup();assert.equal(figure.getAttribute('data-av-fit-policy'),'width');
});

check('floating reserve adds removable pan range and reveal avoids overlay occlusion', () => {
  const {document}=documentFixture(),root=append(document.body,'main'),figure=append(root,'figure',{'data-av-fit-policy':'natural'}),a=fixture(document,figure,{width:300,height:180,viewportWidth:1000,autoHeight:true});
  a.viewport.getBoundingClientRect=()=>({x:0,y:0,left:0,top:0,right:1000,bottom:180,width:1000,height:180});
  a.mark.getBoundingClientRect=()=>({x:760-a.viewport.scrollLeft,y:60,left:760-a.viewport.scrollLeft,top:60,right:800-a.viewport.scrollLeft,bottom:90,width:40,height:30});
  const api=attachPlots(root);assert.equal(a.viewport.getAttribute('data-av-pan'),null);api.reserve(figure,{right:320});
  assert.equal(a.viewport.scrollWidth,1320);assert.equal(a.viewport.getAttribute('data-av-pan'),'ready');assert.equal(a.plot.getAttribute('data-av-zoom'),'1');
  assert.equal(api.reveal(a.mark,{right:320}),true);near(a.viewport.scrollLeft,128);assert.equal(a.plot.getAttribute('data-av-zoom'),'1','Reveal never changes zoom');
  figure.setAttribute('data-av-selection-mode','text');api.reserve(figure);assert.equal(a.viewport.scrollWidth,1000);assert.equal(a.viewport.scrollLeft,0);assert.equal(figure.getAttribute('data-av-selection-mode'),'text','Reserve never changes interaction mode');assert.equal(a.viewport.getAttribute('data-av-pan'),null);api.cleanup();
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
  const editor=append(a.viewport,'input');pointer(editor,'pointerdown');pointer(document,'pointermove',{clientX:-999});pointer(document,'pointerup');assert.equal(a.viewport.scrollLeft,left);a.viewport.scrollLeft=0;send(a.viewport,'scroll');editor.focus();const editorArrow=send(editor,'keydown',{key:'ArrowRight'});assert.equal(editorArrow.defaultPrevented,false);assert.equal(a.viewport.scrollLeft,0,'Pan keyboard handling never consumes arrows inside an editor');
  a.viewport.scrollLeft=0;a.viewport.scrollTop=0;send(a.viewport,'scroll');const arrow=send(a.viewport,'keydown',{key:'ArrowRight'});const down=send(a.viewport,'keydown',{key:'ArrowDown'});assert.equal(arrow.defaultPrevented,true);assert.equal(down.defaultPrevented,true);assert(a.viewport.scrollLeft>0);assert(a.viewport.scrollTop>0,'Focused Pan mode has deterministic keyboard panning');
  for(const mode of ['select','text']){root.setAttribute('data-av-selection-mode',mode);a.viewport.scrollLeft=0;a.viewport.scrollTop=0;send(a.viewport,'scroll');a.viewport.focus();const space=send(a.viewport,'keydown',{key:' '});assert.equal(space.defaultPrevented,true);assert(a.viewport.hasAttribute('data-av-space-pan'));
    pointer(a.mark,'pointerdown');pointer(document,'pointermove',{clientX:50,clientY:70});pointer(document,'pointerup');assert(a.viewport.scrollLeft>0||a.viewport.scrollTop>0,`Space temporarily pans without leaving ${mode} mode`);send(document,'keyup',{key:' '});assert(!a.viewport.hasAttribute('data-av-space-pan'));assert.equal(root.getAttribute('data-av-selection-mode'),mode);}
  root.setAttribute('data-av-selection-mode','select');
  const selectedLeft=a.viewport.scrollLeft;pointer(a.mark,'pointerdown');pointer(document,'pointermove',{clientX:-999});pointer(document,'pointerup');assert.equal(a.viewport.scrollLeft,selectedLeft,'Select mode does not drag-pan after Space is released');root.setAttribute('data-av-selection-mode','pan');
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
