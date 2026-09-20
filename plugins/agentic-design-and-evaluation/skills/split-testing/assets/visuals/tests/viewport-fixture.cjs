// Explicit geometry/event model for viewport mechanics; no CSS or browser engine.
const { DocumentDouble, append, send, click } = require('./dom-double.cjs');

function documentFixture({ events = false, observer = false } = {}) {
  const document = new DocumentDouble(), observers = [];
  if (events) document.defaultView.CustomEvent = class {
    constructor(type, options) { this.type = type; Object.assign(this, options); this.defaultPrevented = false; }
  };
  if (observer) document.defaultView.ResizeObserver = class {
    constructor(callback) { this.callback = callback; this.targets = []; this.disconnected = false; observers.push(this); }
    observe(element) { this.targets.push(element); }
    disconnect() { this.disconnected = true; }
    trigger() { if (!this.disconnected) this.callback([]); }
  };
  return { document, observers };
}

function fixture(document, parent, options = {}) {
  const width = options.width || 600, height = options.height || 400;
  const x = options.x || 0, y = options.y || 0;
  const plot = append(parent, 'div', { class: 'av-plot-shell' + (options.coupledRows ? ' av-row-plot' : ''), 'data-av-plot': '', ...(options.key ? { 'data-av-plot-key': options.key } : {}) });
  const toolbar = append(plot, 'div', { 'data-av-controls': '' });
  const fit = append(toolbar, 'button', { 'data-av-fit-width': '' }, 'Fit width');
  const actual = append(toolbar, 'button', { 'data-av-actual-size': '' }, 'Actual size');
  const plus = append(toolbar, 'button', { 'data-av-zoom-in': '' }, '+');
  const minus = append(toolbar, 'button', { 'data-av-zoom-out': '' }, '−');
  const reset = append(toolbar, 'button', { 'data-av-zoom-reset': '' }, 'Reset');
  const layout = append(plot, 'div', { class: 'av-row-plot-layout' });
  const viewport = append(layout, 'div', { class: 'av-plot-scroll' });
  viewport.clientWidth = options.viewportWidth ?? 300; viewport.clientHeight = options.viewportHeight ?? 200;
  if (options.autoHeight) {
    let fallback = viewport.clientHeight;
    Object.defineProperty(viewport, 'clientHeight', { get: () => Number.parseFloat(plot.style.getPropertyValue('--av-plot-fit-height')) || fallback, set: value => { fallback = value; } });
  }
  const initialStyle = options.minimumWidth ? `color:blue;min-width:${options.minimumWidth}px` : 'color:blue';
  const svg = append(viewport, 'svg', { 'data-av-zoom-target': '', width: String(width), height: String(height), viewBox: `${x} ${y} ${width} ${height}`, style: initialStyle });
  append(svg, 'title', {}, options.title || 'Observed values');
  const mark = append(svg, 'g', { 'data-av-inspect': 'original', 'aria-pressed': 'false' }, 'Original zero 0 and missingness');
  const sourcePoint = { x: x + 390, y: y + 175 };
  mark.getBBox = () => ({ x: sourcePoint.x - 2, y: sourcePoint.y - 2, width: 4, height: 4 });
  const rect = () => {
    const intrinsicWidth = Number(svg.getAttribute('width')), intrinsicHeight = Number(svg.getAttribute('height'));
    const explicit = Number.parseFloat(svg.style.getPropertyValue('width'));
    const authored = options.responsive ? viewport.clientWidth : options.renderedWidth ?? intrinsicWidth;
    const minimum = Number.parseFloat(svg.style.getPropertyValue('min-width')) || 0;
    const visible = options.coupledRows ? layout.clientWidth > 0 : viewport.clientWidth > 0;
    const rendered = visible ? Math.max(minimum, Number.isFinite(explicit) ? explicit : authored) : 0;
    return { x: 0, y: 0, left: 0, top: 0, width: rendered, height: rendered * intrinsicHeight / intrinsicWidth };
  };
  svg.getBoundingClientRect = rect;
  Object.defineProperty(viewport, 'scrollWidth', { get: () => Math.max(viewport.clientWidth, rect().width) });
  Object.defineProperty(viewport, 'scrollHeight', { get: () => Math.max(viewport.clientHeight, rect().height) });
  const captured = [], released = [];
  viewport.setPointerCapture = id => captured.push(id); viewport.releasePointerCapture = id => released.push(id);
  let xAxis, rows;
  if (options.layers) {
    const rowWidth = options.rowWidth || 185, axisHeight = options.axisHeight || 64;
    const xViewport = append(layout, 'div', { 'data-av-axis-viewport': 'x' });
    xAxis = append(xViewport, 'svg', { 'data-av-axis-layer': 'x', width: String(width), height: String(axisHeight), viewBox: `${x} 0 ${width} ${axisHeight}` });
    append(xAxis, 'text', {}, 'Exact axis and unit');
    const rowViewport = append(layout, 'div', { 'data-av-axis-viewport': 'rows' });
    rows = append(rowViewport, 'svg', { 'data-av-axis-layer': 'rows', width: String(rowWidth), height: String(height), viewBox: `0 ${y} ${rowWidth} ${height}` });
    const row = append(rows, 'g', { 'data-av-row-center':'175' }); append(row, 'text', { y:'175' }, 'Original row identity');
    if (options.coupledRows) {
      plot.style.setProperty('--av-axis-row-width', rowWidth + 'px');
      layout.clientWidth = options.availableWidth || 540;
      Object.defineProperty(rowViewport, 'clientWidth', { get: () => Math.min(Number.parseFloat(plot.style.getPropertyValue('--av-axis-row-width')) || rowWidth, options.rowCap ?? Infinity) });
      Object.defineProperty(viewport, 'clientWidth', { get: () => Math.max(0, layout.clientWidth - rowViewport.clientWidth) });
    }
  }
  return { plot, layout, toolbar, viewport, svg, mark, sourcePoint, rect, fit, actual, plus, minus, reset, xAxis, rows, captured, released };
}

function pointer(target, type, extra = {}) {
  return send(target, type, { pointerId: 7, pointerType: 'mouse', isPrimary: true, button: 0, buttons: 1, clientX: 100, clientY: 100, ...extra });
}

module.exports = { documentFixture, fixture, pointer, append, send, click };
