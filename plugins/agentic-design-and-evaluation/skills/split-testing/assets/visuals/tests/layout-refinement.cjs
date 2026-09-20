// Actual renderer/refiner contracts with bounded font and DOM models.
const assert = require('node:assert/strict'), path = require('node:path');
const { fixture, V, attachLayoutRefinement, append, send } = require('./parsed-dom-fixture.cjs');
const { attachPlots } = require(path.join(process.argv[2], 'plot-navigation.js'));

{
  const {d, parse} = fixture();
  const input = {id:'scatter-original',title:'Actual evidence',xAxis:'Elapsed time and the conditions retained in the supplied assignment',yAxis:'Recovery effort',points:[{id:'a',label:'First observation',groupId:'same',group:'Run',x:1,y:2},{id:'b',label:'Second observation',groupId:'same',group:'Run',x:3,y:4}]};
  const content = parse(V.scatterPlot(input)), frame = content.querySelector('.av-card'); d.body.appendChild(frame);
  const svg = frame.querySelector('[data-av-zoom-target]'), mark = svg.querySelector('[data-av-inspect]'); mark.classList.add('av-selected'); mark.setAttribute('tabindex','0'); mark.focus();
  const table = frame.querySelector('.av-data'), tableText = table.textContent, originalViewBox = svg.getAttribute('viewBox');
  const cleanup = attachLayoutRefinement(frame);
  send(svg.closest('[data-av-plot]'), 'av-layout-request', { detail:{width:480,mode:'fit'} });
  assert.equal(frame.querySelector('[data-av-zoom-target]'), svg, 'The viewport target itself must survive refinement');
  assert.equal(svg.querySelector('[data-av-inspect]'), mark, 'A selected live mark must retain its identity');
  assert.equal(mark.classList.contains('av-selected'), true); assert.equal(d.activeElement, mark);
  assert.notEqual(svg.getAttribute('viewBox'), originalViewBox); assert.equal(frame.querySelector('.av-data'), table); assert.equal(table.textContent, tableText);
  assert.equal(frame.querySelector('[data-av-layout-status]'), null);
  cleanup(); assert.equal(svg.getAttribute('viewBox'), originalViewBox); assert.equal(svg.querySelector('[data-av-inspect]'), mark); assert.equal(d.listenerCount, 0);
}
{
  const {d, parse} = fixture();
  const outer = append(d.body,'section',{class:'av-card'}), content = parse(V.intervalPlot({title:'Nested interval',axis:'Exact value',intervalLabel:'Observed bounds',items:[{label:'A long label with original Unicode 👩🏽‍🚀 é and all its qualifications',low:1,high:3}]}));
  const child = content.querySelector('.av-card'); outer.appendChild(child);
  const cleanup = attachLayoutRefinement(outer), dialog = append(d.body,'dialog'); dialog.appendChild(child);
  const svg = child.querySelector('[data-av-zoom-target]'), before = svg.getAttribute('viewBox');
  send(svg.closest('[data-av-plot]'),'av-layout-request',{detail:{width:450,availableWidth:635,mode:'fit'}});
  assert.notEqual(svg.getAttribute('viewBox'),before,'Captured layout ownership must survive movement outside the original root');
  assert.equal(child.querySelectorAll('[data-av-axis-layer]').length,2); assert.equal(child.querySelector('[data-av-layout-status]'),null);
  cleanup();assert.equal(svg.getAttribute('viewBox'),before);
}
(async () => {
  const {d, parse} = fixture();
  d.defaultView.CustomEvent = class { constructor(type, options = {}) { this.type = type; this.bubbles = false; Object.assign(this, options); } };
  let finishFonts; d.fonts = {ready: new Promise(resolve => finishFonts = resolve)};
  const host = append(d.body, 'section'), frame = parse(V.intervalPlot({title:'Late fonts',axis:'Measured value',intervalLabel:'Observed interval',items:[{label:'Original complete qualification',low:1,high:4}]})).querySelector('.av-card'); host.appendChild(frame);
  const plot = frame.querySelector('[data-av-plot]'), svg = plot.querySelector('[data-av-zoom-target]');
  const cleanup = attachLayoutRefinement(host); let invalidations = 0;
  const controller = () => { invalidations++; send(plot,'av-layout-request',{detail:{width:360,availableWidth:500,mode:'fit'}}); };
  plot.addEventListener('av-layout-invalidated', controller);
  send(plot,'av-layout-request',{detail:{width:360,availableWidth:500,mode:'fit'}});
  const fitted = svg.getAttribute('viewBox');
  // Inspection can move the owned frame before fonts are ready.
  append(d.body,'dialog').appendChild(frame);
  finishFonts(); await d.fonts.ready; await Promise.resolve();
  assert.equal(invalidations,1,'Font changes must return to the viewport owner even after the frame moves');
  assert.equal(svg.getAttribute('viewBox'),fitted,'Font readiness must preserve the active Fit layout');
  plot.removeEventListener('av-layout-invalidated',controller); cleanup();
  // Use the actual scatter renderer, refiner and viewport owner together. A frame
  // may contain several plots, with different modes and a hidden complete-pairs view.
  for (const viewportWidth of [420, 680]) for (const trigger of ['late-fonts', 'sibling-zoom', 'sibling-reset']) {
    const {d, parse} = fixture();
    d.defaultView.CustomEvent = class { constructor(type, options = {}) { this.type = type; this.bubbles = false; Object.assign(this, options); } };
    let finishFonts; d.fonts = {ready: new Promise(resolve => finishFonts = resolve)};
    const input = {id:'mixed-viewports',title:'Paired and partial observations',xAxis:'Elapsed time',yAxis:'Effort',points:[{id:'a',label:'First',x:1,y:2},{id:'b',label:'Second',x:3,y:4},{id:'x-only',label:'Only elapsed time was observed',x:100,y:null},{id:'y-only',label:'Only effort was observed',x:null,y:40}]};
    const frame = parse(V.scatterPlot(input)).querySelector('.av-card'); d.body.appendChild(frame);
    const plots = [...frame.querySelectorAll('[data-av-plot]')];
    const main = frame.querySelector('[data-av-coordinate-scope="known"]').querySelector('[data-av-plot]');
    const complete = frame.querySelector('[data-av-coordinate-scope="complete"]').querySelector('[data-av-plot]');
    const bands = [...frame.querySelectorAll('.av-missing-coordinate-band')].map(band => band.querySelector('[data-av-plot]'));
    assert.equal(plots.length, 4); assert.equal(bands.length, 2);
    for (const plot of plots) {
      const svg = plot.querySelector('[data-av-zoom-target]'), viewport = svg.parentElement;
      const row = plot.querySelector('[data-av-axis-layer="rows"]'), layout = plot.querySelector('.av-row-plot-layout');
      const visible = () => !plot.closest('[hidden]');
      // Model the emitted row track and its 35% CSS cap, not a browser layout engine.
      const rowTrack = () => Math.min(viewportWidth * .35, Number.parseFloat(plot.style.getPropertyValue('--av-axis-row-width')) || Number(row?.getAttribute('width')) || 0);
      if (row) { layout.clientWidth = viewportWidth; Object.defineProperty(row.parentElement, 'clientWidth', {get:rowTrack}); }
      Object.defineProperty(viewport, 'clientWidth', {get:() => visible() ? viewportWidth - (row ? rowTrack() : 0) : 0});
      viewport.clientHeight = 200;
      svg.getBoundingClientRect = () => {
        const width = visible() ? Number.parseFloat(svg.style.getPropertyValue('width')) || Number(svg.getAttribute('width')) : 0;
        return {x:0,y:0,left:0,top:0,width,height:width * Number(svg.getAttribute('height')) / Number(svg.getAttribute('width'))};
      };
      Object.defineProperty(viewport, 'scrollWidth', {get:() => Math.max(viewport.clientWidth, svg.getBoundingClientRect().width)});
      Object.defineProperty(viewport, 'scrollHeight', {get:() => Math.max(viewport.clientHeight, svg.getBoundingClientRect().height)});
    }
    const geometry = plot => [...plot.querySelectorAll('svg[data-av-zoom-target],svg[data-av-axis-layer]')].map(svg => ({svg,viewBox:svg.getAttribute('viewBox'),width:svg.getAttribute('width'),height:svg.getAttribute('height')}));
    const mainSVG = main.querySelector('[data-av-zoom-target]'), mark = mainSVG.querySelector('[data-av-inspect]');
    mark.classList.add('av-selected'); mark.setAttribute('tabindex', '0'); mark.focus();
    const table = frame.querySelector('.av-data'), tableText = table.textContent, source = frame.getAttribute('data-av-layout-input');
    const initialGeometry = plots.map(geometry), cleanupLayout = attachLayoutRefinement(frame), navigation = attachPlots(frame);
    assert.equal(navigation.click(main.querySelector('[data-av-zoom-reset]')), true);
    const fitted = geometry(main), hidden = geometry(complete);
    assert.equal(Number(mainSVG.getAttribute('width')), viewportWidth, 'Fit must reflow at the available width');
    assert.equal(mainSVG.getBoundingClientRect().width, viewportWidth);
    assert.deepEqual(geometry(complete), initialGeometry[plots.indexOf(complete)], 'Fitting a visible plot must not rewrite a hidden sibling');
    if (trigger === 'late-fonts') {
      finishFonts(); await d.fonts.ready; await Promise.resolve();
    } else {
      const otherBand = geometry(bands[1]);
      if (trigger === 'sibling-reset') navigation.click(bands[0].querySelector('[data-av-zoom-in]'));
      navigation.click(bands[0].querySelector(trigger === 'sibling-reset' ? '[data-av-zoom-reset]' : '[data-av-zoom-in]'));
      assert.deepEqual(geometry(bands[1]), otherBand, 'Only the requesting band and its axes may reflow');
      if (trigger === 'sibling-reset') {
        const bandSVG = bands[0].querySelector('[data-av-zoom-target]'), axis = bands[0].querySelector('[data-av-axis-layer="x"]');
        assert.ok(Number(bandSVG.getAttribute('width')) < Number(initialGeometry[plots.indexOf(bands[0])].find(scene => scene.svg === bandSVG).width), 'Equal-width sibling requests must each reflow; the cache is not frame-wide');
        assert.equal(axis.getAttribute('width'), bandSVG.getAttribute('width'), 'The requesting plot retains synchronized axis geometry');
      }
    }
    navigation.refresh();
    assert.deepEqual(geometry(main), fitted, `${trigger} must preserve the fitted sibling's source geometry`);
    assert.deepEqual(geometry(complete), hidden, 'A hidden complete-pairs scene retains its own geometry');
    assert.equal(main.getAttribute('data-av-viewport-mode'), 'fit');
    assert.equal(mainSVG.getBoundingClientRect().width / Number(mainSVG.getAttribute('width')), 1, 'Fit must retain readable scale instead of shrinking a restored wide viewBox');
    assert.equal(mainSVG.querySelector('[data-av-inspect]'), mark); assert.equal(d.activeElement, mark); assert.ok(mark.classList.contains('av-selected'));
    assert.equal(frame.getAttribute('data-av-layout-input'), source); assert.equal(frame.querySelector('.av-data'), table); assert.equal(table.textContent, tableText);
    assert.equal(frame.querySelector('[data-av-layout-status]'), null);
    navigation.cleanup(); cleanupLayout();
    assert.deepEqual(plots.map(geometry), initialGeometry, 'Cleanup restores every owned scene and axis independently');
    assert.equal(d.listenerCount, 0);
  }
  console.log('native-metric refinement contracts passed (explicit font/DOM doubles)');
})().catch(error => { console.error(error); process.exitCode=1; });
