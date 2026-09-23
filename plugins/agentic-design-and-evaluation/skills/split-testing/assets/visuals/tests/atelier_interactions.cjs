// Deliberately bounded, hand-built DOM/event doubles. These check source state
// transitions; they do not prove browser layout, native focus trapping or AT use.
const assert = require("node:assert/strict");
const path = require("node:path");
const { enhanceVisuals } = require(path.join(process.argv[2], "interaction.js"));
const { indexedDBDouble, storageWindow } = require("./reader-storage.cjs");
const { fixture: viewportFixture } = require("./viewport-fixture.cjs");

const { EventSurface, NodeDouble, TextDouble, ElementDouble, DialogDouble, WindowDouble, DocumentDouble, element, append, send, click } = require("./dom-double.cjs");

function fixtureCard(document, parent = document.body, id = "observations") {
  const card = append(parent, "section", { class: "av-card", id });
  const header = append(card, "header"); append(header, "h2", {}, "Observed failures & missingness");
  const tools = append(header, "div", { "data-av-controls": "", hidden: "" });
  const focus = append(tools, "button", { "data-av-focus": "" }, "Focus");
  const plot = append(card, "div", { class: "av-plot-shell", "data-av-plot": "", "data-av-content-view": "visual" });
  const plotControls = append(plot, "div", { "data-av-controls": "", hidden: "" });
  const zoomIn = append(plotControls, "button", { "data-av-zoom-in": "" }, "Enlarge");
  const zoomOut = append(plotControls, "button", { "data-av-zoom-out": "" }, "Reduce");
  const zoomReset = append(plotControls, "button", { "data-av-zoom-reset": "" }, "Reset zoom");
  const scroll = append(plot, "div", { class: "av-plot-scroll" });
  const svg = append(scroll, "svg", { "data-av-zoom-target": "", width: "900", height: "400", style: "color:blue" });
  append(svg, "text", {}, "All supplied observations");
  const data = append(card, "details", { "data-av-content-view": "data", id: `${id}-data` });
  append(data, "summary", {}, "Data and annotations"); append(data, "p", {}, "Failed 0.015. Missing: outage case. Exception: one timeout.");
  const input = append(card, "input", { value: "original" });
  return { card, focus, tools, plot, data, input, svg, zoomIn, zoomOut, zoomReset };
}
function fixtureWorkspace(document, name) {
  const root = append(document.body, "main", { class: "av-workspace", id: name });
  const header = append(root, "header");
  const searchArea = append(header, "div", { "data-av-script-only": "", hidden: "" });
  const label = append(searchArea, "label", {}, "Search evidence"); const search = append(label, "input", { "data-av-search": "", type: "search" });
  const status = append(searchArea, "p", { "data-av-search-status": "", role: "status" }, "Original status");
  const showAll = append(searchArea, "button", { "data-av-show-all": "" }, "Show all views");
  const nav = append(header, "nav");
  const firstNav = append(nav, "a", { "data-av-view": "start", href: `#${name}--view-start` }, "Start");
  const secondNav = append(nav, "a", { "data-av-view": "exceptions", href: `#${name}--view-exceptions` }, "Exceptions");
  const first = append(root, "section", { "data-av-panel": "start", id: `${name}--view-start` }); append(first, "h2", {}, "Start"); append(first, "p", {}, "Scope and context.");
  const link = append(first, "a", { href: `#${name}-failure` }, "Retained exception");
  const second = append(root, "section", { "data-av-panel": "exceptions", id: `${name}--view-exceptions` }); append(second, "h2", {}, "Exceptions");
  const details = append(second, "details"); append(details, "summary", {}, "All observations");
  const failure = append(details, "p", { id: `${name}-failure` }, "Failed case: DEADLOCK. Missing specimen: zeta.");
  append(details, "img", { alt: "Diagnostic trace omega", src: "data:image/png;base64,AA==" });
  const footer = append(root, "footer", { class: "av-workspace-footer" }); append(footer, "p", { id: `${name}-footnote` }, "Footnote provenance: original source.");
  return { root, searchArea, search, status, showAll, firstNav, secondNav, first, second, details, failure, link, footer };
}
function fixtureExplorer(document, parent) {
  const explorer = append(parent, "div", { "data-av-explorer": "" });
  const tools = append(explorer, "div", { "data-av-controls": "", hidden: "" });
  const select = append(tools, "select", { "data-av-select": "" }); append(select, "option", { value: "" }, "Choose object");
  const previous = append(tools, "button", { "data-av-step": "-1" }, "Previous");
  const next = append(tools, "button", { "data-av-step": "1" }, "Next");
  const drawing = append(explorer, "svg", { role: "img", "aria-label": "Supplied relationships" });
  const nodes = [], objects = [], compare = [];
  for (let index = 0; index < 3; index++) {
    const key = `object-${index}`;
    append(select, "option", { value: key }, `Object ${index}`);
    nodes.push(append(drawing, "g", { "data-av-inspect": key }, `Object ${index}`));
    compare.push(append(tools, "input", { type: "checkbox", "data-av-compare": key }));
    const object = append(explorer, "details", { "data-av-object": key });
    append(object, "summary", {}, `Object ${index}`); append(object, "p", {}, `Original evidence ${index}. Missing or failed values retained.`); objects.push(object);
  }
  const edge = append(drawing, "path", { "data-av-from": "object-0", "data-av-to": "object-1" });
  return { explorer, select, previous, next, nodes, objects, edge, compare, drawing };
}

function fixtureStorage(document, entries = [], factory = indexedDBDouble()) {
  const store = storageWindow(factory, entries);
  document.defaultView.indexedDB = factory; document.defaultView.localStorage = store.localStorage;
  return store;
}
function stored(store, key) { const record = store.indexedDB.records.get(key); assert.ok(record, `Missing typed record ${key}`); return record; }
function databaseWrites(store) { return store.indexedDB.calls.filter(([operation]) => operation === "put").length; }

(async () => {

// Live frame movement, exact state/identity, asynchronous native close handling,
// scoped data modes, cleanup and repeat hydration.
{
  const document = new DocumentDouble(), root = append(document.body, "main");
  const frame = fixtureCard(document, root), nested = fixtureCard(document, frame.card, "nested");
  const sibling = append(root, "p", {}, "After frame");
  const cleanup = enhanceVisuals(root);
  assert.equal(enhanceVisuals(root), cleanup);
  assert.equal(frame.tools.hidden, false);
  assert.equal(frame.card.querySelectorAll("[data-av-view-toggle]").length, 2);
  click(frame.card.querySelector('[data-av-view-toggle="data"]'));
  assert.equal(frame.plot.hidden, true); assert.equal(frame.data.open, true); assert.equal(nested.plot.hidden, false);
  assert.match(frame.data.textContent, /Missing: outage case/);
  click(frame.card.querySelector('[data-av-view-toggle="visual"]'));
  assert.equal(frame.plot.hidden, false); assert.equal(frame.data.open, true);
  frame.input.value = "user text";
  const originalParent = frame.card.parentNode;
  click(frame.focus);
  const dialog = root.querySelector("dialog");
  assert.equal(dialog.open, true); assert.equal(dialog.getAttribute("aria-label"), "Expanded view: Observed failures & missingness");
  assert.equal(frame.card.parentElement.className, "av-dialog-body");
  assert.equal(document.getElementById("observations"), frame.card);
  assert.equal(document.body.querySelectorAll('[id="observations"]').length, 1);
  assert.equal(frame.input.value, "user text"); assert.equal(frame.data.open, true);
  assert.equal(frame.focus.hidden, true); assert.equal(nested.focus.hidden, false);
  const placeholder = originalParent.querySelector(".av-focus-placeholder");
  assert.ok(placeholder); assert.equal(placeholder.textContent, ""); assert.equal(placeholder.id, "");
  click(dialog.querySelector("[data-av-close-focus]"));
  assert.equal(frame.card.parentNode, originalParent); assert.equal(frame.card.nextSibling, sibling); assert.equal(document.activeElement, frame.focus); assert.equal(frame.focus.hidden, false); assert.equal(originalParent.querySelector(".av-focus-placeholder"), null);
  click(frame.focus); document.flush(); // Old queued close must not restore the reopened frame.
  assert.equal(dialog.open, true); assert.equal(frame.card.parentElement.className, "av-dialog-body");
  const cancel = send(dialog, "cancel", { bubbles: false }); assert.equal(cancel.defaultPrevented, true);
  assert.equal(frame.card.parentNode, originalParent); document.flush();
  click(frame.focus); cleanup(); cleanup(); document.flush();
  assert.equal(frame.card.parentNode, originalParent); assert.equal(frame.tools.hidden, true);
  assert.equal(frame.data.open, false); assert.equal(frame.input.value, "user text");
  assert.equal(root.querySelector("dialog"), null); assert.equal(root.querySelector("[data-av-view-toggle]"), null);
  assert.equal(root.listenerCount, 0); assert.equal(document.listenerCount, 0); assert.equal(document.defaultView.listenerCount, 0); assert.equal(document.defaultView.media.listenerCount, 0);
  assert.equal(frame.focus.getAttribute("aria-expanded"), null); assert.equal(root.hasAttribute("data-av-enhanced"), false);
  const again = enhanceVisuals(root); assert.notEqual(again, cleanup); again();
}

// Enhancing a frame as the root must not process bubbling controls twice.
{
  const document = new DocumentDouble(), frame = fixtureCard(document);
  const nested = fixtureCard(document, frame.card, "nested-root");
  const explorer = fixtureExplorer(document, frame.card);
  const cleanup = enhanceVisuals(frame.card);
  click(nested.focus); assert.equal(document.body.querySelector("dialog").open, true);
  click(frame.focus); assert.equal(document.body.querySelector("dialog").open, true);
  assert.equal(frame.card.parentElement.className, "av-dialog-body");
  send(explorer.nodes[1], "keydown", { key: " " }); assert.equal(explorer.objects[1].open, true);
  explorer.select.value = "object-2"; send(explorer.select, "change"); assert.equal(explorer.objects[2].open, true);
  click(frame.focus); assert.equal(frame.card.parentNode, document.body);
  click(frame.focus); click(document.body.querySelector("[data-av-close-focus]"));
  assert.equal(document.activeElement, frame.focus); cleanup(); document.flush();
  assert.equal(document.body.querySelector("dialog"), null);
}
// A nested frame focused before its standalone parent leaves that root's event
// path. Keyboard, selectors, comparison and disclosure motion must still work.
{
  const document = new DocumentDouble(), frame = fixtureCard(document);
  const nested = fixtureCard(document, frame.card, "focused-child");
  const explorer = fixtureExplorer(document, nested.card);
  const cleanup = enhanceVisuals(frame.card);
  click(nested.focus);
  const dialog = document.body.querySelector("dialog");
  assert.equal(frame.card.contains(nested.card), false);
  assert.equal(dialog.contains(nested.card), true);
  const key = send(explorer.nodes[1], "keydown", { key: "Enter" });
  assert.equal(key.defaultPrevented, true); assert.equal(explorer.objects[1].open, true);
  assert.equal(document.activeElement, explorer.objects[1].querySelector("summary"));
  explorer.select.focus(); explorer.select.value = "object-2"; send(explorer.select, "change");
  assert.equal(explorer.objects[2].open, true); assert.equal(document.activeElement, explorer.select);
  explorer.compare[0].checked = true; send(explorer.compare[0], "change");
  explorer.compare[2].checked = true; send(explorer.compare[2], "change");
  assert.equal(explorer.explorer.classList.contains("av-comparing"), true);
  assert.deepEqual(explorer.explorer.querySelectorAll("[data-av-object]"), [explorer.objects[0], explorer.objects[2], explorer.objects[1]]);
  const motions = document.animations.length;
  explorer.objects[1].open = true;
  send(explorer.objects[1], "toggle", { bubbles: false });
  assert.equal(document.animations.length, motions + 1);
  click(dialog.querySelector("[data-av-close-focus]"));
  assert.equal(nested.card.parentNode, frame.card); assert.equal(document.activeElement, nested.focus);
  // Moving the entire root must not dispatch events twice through its dialog.
  click(frame.focus);
  const before = document.animations.length;
  send(explorer.nodes[0], "keydown", { key: " " });
  assert.equal(document.animations.length, before + 1);
  cleanup(); document.flush();
  assert.equal(nested.card.parentNode, frame.card); assert.equal(frame.card.parentNode, document.body);
  assert.deepEqual(explorer.explorer.querySelectorAll("[data-av-object]"), explorer.objects);
  assert.equal(document.body.querySelector("dialog"), null); assert.equal(dialog.listenerCount, 0);
}

for (const unavailable of ["noDialog", "rejectDialog"]) {
  const document = new DocumentDouble(); document[unavailable] = true;
  const frame = fixtureCard(document), cleanup = enhanceVisuals(frame.card);
  click(frame.focus); assert.equal(frame.card.parentNode, document.body); assert.equal(document.activeElement, frame.card);
  assert.equal(frame.card.classList.contains("av-focused"), false); cleanup();
}

// Search finds retained evidence without replacing the current reading context.
// A chosen result opens the original object; full-report mode remembers the section.
{
  const document = new DocumentDouble(), a = fixtureWorkspace(document, "alpha"), b = fixtureWorkspace(document, "beta");
  const cleanA = enhanceVisuals(a.root), cleanB = enhanceVisuals(b.root);
  const single = a.root.querySelector("[data-av-show-single]");
  assert.equal(a.second.hidden, true); assert.equal(a.searchArea.hidden, false);
  const evidenceBefore = a.second.textContent;
  a.search.value = " deadLOCK "; send(a.search, "input");
  assert.equal(a.first.hidden, false); assert.equal(a.second.hidden, true); assert.equal(a.details.open, false);
  assert.equal(a.second.textContent, evidenceBefore); assert.match(a.root.querySelector("[data-av-search-results]").textContent, /1 result/);
  assert.equal(b.first.hidden, false); assert.equal(b.second.hidden, true);
  assert.equal(a.firstNav.getAttribute("aria-current"), "page");
  const hit = a.root.querySelector("[data-av-search-hit]");
  const arrow = send(a.search, "keydown", { key: "ArrowDown" }); assert.equal(arrow.defaultPrevented, true); assert.equal(document.activeElement, hit);
  send(hit, "keydown", { key: "ArrowUp" }); assert.equal(document.activeElement, a.search);
  click(hit);
  assert.equal(a.first.hidden, true); assert.equal(a.second.hidden, false); assert.equal(a.details.open, true);
  assert.equal(document.activeElement, a.failure); assert.equal(a.search.value, "");
  click(a.showAll); assert.equal(a.first.hidden, false); assert.equal(a.second.hidden, false); assert.match(a.status.textContent, /Full report/);
  click(single); assert.equal(a.first.hidden, true); assert.equal(a.second.hidden, false);
  assert.equal(single.getAttribute("aria-pressed"), "true"); assert.equal(a.showAll.getAttribute("aria-pressed"), "false");
  a.search.value = "omega"; send(a.search, "input"); assert.match(a.root.querySelector("[data-av-search-results]").textContent, /1 result/);
  a.search.value = "does not exist"; send(a.search, "input");
  assert.equal(a.first.hidden, true); assert.equal(a.second.hidden, false); assert.match(a.root.querySelector("[data-av-search-results]").textContent, /No matches/);
  send(a.search, "keydown", { key: "Escape" }); assert.equal(a.search.value, ""); assert.equal(a.second.hidden, false);
  click(a.firstNav); a.details.open = false;
  const fragmentClick = click(a.link);
  assert.equal(fragmentClick.defaultPrevented, false); assert.equal(a.first.hidden, true); assert.equal(a.second.hidden, false); assert.equal(a.details.open, true); assert.equal(document.activeElement, a.failure);
  click(a.firstNav); document.defaultView.location.hash = "#alpha-failure"; send(document.defaultView, "hashchange"); assert.equal(a.second.hidden, false);
  click(a.firstNav); click(a.secondNav, { ctrlKey: true }); assert.equal(a.second.hidden, true);
  const crossLink = append(a.first, "a", { href: "#beta-failure" }, "Other workspace evidence");
  document.defaultView.location.hash = "#beta-failure"; click(b.firstNav); click(crossLink);
  assert.equal(b.second.hidden, false); assert.equal(b.details.open, true); assert.equal(document.activeElement, b.failure);
  a.search.value = "provenance"; send(a.search, "input"); assert.match(a.root.querySelector("[data-av-search-results]").textContent, /1 result/); assert.equal(a.footer.hidden, false);
  a.search.value = "<img onerror=alert(1)>"; send(a.search, "input"); assert.match(a.root.querySelector("[data-av-search-results]").textContent, /No matches/);
  assert.equal(a.status.childNodes.length, 1); assert.equal(a.status.childNodes[0].nodeType, 3);
  click(a.root.querySelector("[data-av-search-reset]")); assert.equal(document.activeElement, a.search);
  cleanA(); cleanB();
  assert.equal(a.first.hidden, false); assert.equal(a.second.hidden, false); assert.equal(a.searchArea.hidden, true);
  assert.equal(a.status.textContent, "Original status"); assert.equal(a.root.querySelector("[data-av-search-reset]"), null);
  assert.equal(a.failure.getAttribute("tabindex"), null); assert.equal(a.firstNav.getAttribute("aria-current"), null);
  assert.equal(document.listenerCount, 0);
}

// Hash-based entry opens nested disclosures on first hydration, even though a
// different view is normally selected, and grouped roots retain independence.
{
  const document = new DocumentDouble(), a = fixtureWorkspace(document, "first"), b = fixtureWorkspace(document, "second");
  document.defaultView.location.hash = "#first-failure";
  const cleanup = enhanceVisuals(document.body);
  assert.equal(a.second.hidden, false); assert.equal(a.details.open, true); assert.equal(b.second.hidden, true);
  click(b.secondNav); assert.equal(a.second.hidden, false); assert.equal(b.second.hidden, false);
  cleanup();
}

// Initial deep links settle again after delayed diagram layout, without moving
// focus. A reader navigation while that render is pending cancels the correction,
// so the old entry fragment cannot pull the reader back later. This is a DOM /
// controllable-runtime contract; native browser scroll geometry is tested separately.
for (const readerTakesOver of [false, true]) {
  const document = new DocumentDouble(), nativeCreate = document.createElement.bind(document);
  document.defaultView.getComputedStyle = node => ({ fontFamily: "Fixture Sans", font: "14px Fixture Sans", color: "rgb(20, 30, 40)", transform: "none", overflowX: "visible", overflowY: "visible", getPropertyValue: name => node.style?.getPropertyValue?.(name) || "" });
  document.createElement = tag => {
    if (tag !== "template") return nativeCreate(tag);
    const template = nativeCreate("template"), content = nativeCreate("fragment"); template.content = content;
    Object.defineProperty(template, "innerHTML", { set() { content.replaceChildren(); const svg = nativeCreate("svg"); svg.setAttribute("width", "200"); svg.setAttribute("height", "100"); append(svg, "text", {}, "Rendered late diagram"); content.appendChild(svg); } });
    return template;
  };
  let releaseRender = null, phase = "entry";
  document.defaultView.mermaid = {
    initialize() {}, async parse() { return { config: {} }; },
    async render() { await new Promise(resolve => { releaseRender = resolve; }); return { svg: "<svg width=\"200\" height=\"100\"><text>Rendered late diagram</text></svg>" }; },
    getRegisteredDiagramsMetadata() { return []; },
  };
  const root = append(document.body, "main", { id: readerTakesOver ? "takeover-root" : "settle-root" });
  const destination = append(root, "p", { id: readerTakesOver ? "reader-choice" : "settled-choice" }, "Reader-owned destination");
  const link = append(root, "a", { href: "#" + destination.id }, "Choose another passage");
  const figure = append(root, "figure", { id: readerTakesOver ? "late-takeover" : "late-settle", "data-av-figure": "", "data-av-figure-title": "Late diagram" });
  append(figure, "figcaption", {}, "Late diagram"); const body = append(figure, "div", { "data-av-figure-body": "" });
  const diagram = append(body, "div", { "data-av-mermaid": "", "data-av-mermaid-source": "flowchart LR\n A --> B" }); append(diagram, "p", { "data-av-mermaid-status": "" }, "Diagram source available");
  const output = append(diagram, "div", { "data-av-mermaid-output": "" }), placeholder = append(output, "svg", { width: "200", height: "100" }); append(placeholder, "text", {}, "Placeholder");
  const entryScrolls = [], destinationScrolls = []; figure.scrollIntoView = options => entryScrolls.push({ phase, options }); destination.scrollIntoView = options => destinationScrolls.push({ phase, options });
  document.defaultView.location.hash = "#" + figure.id; const cleanup = enhanceVisuals(root);
  assert.equal(entryScrolls.length, 1, "Entry fragment is revealed immediately"); assert.equal(document.activeElement, figure);
  await new Promise(resolve => setImmediate(resolve)); assert.equal(typeof releaseRender, "function", "Delayed Mermaid render is in flight");
  if (readerTakesOver) { phase = "reader"; click(link); assert.equal(document.activeElement, destination); assert.equal(destinationScrolls.length, 1); assert.equal((document.listeners.get("wheel")||[]).length,0,"Reader takeover removes temporary settle listeners immediately"); }
  phase = "settled"; releaseRender(); await cleanup.whenIdle();
  if (readerTakesOver) { assert.equal(entryScrolls.length, 1, "Reader navigation cancels late entry-fragment settling"); assert.equal(document.activeElement, destination); }
  else { assert.equal(entryScrolls.length, 2, "Entry fragment is corrected once after delayed layout settles"); assert.equal(entryScrolls.at(-1).phase, "settled"); assert.equal(document.activeElement, figure, "Settling scroll does not replace fragment focus"); }
  assert.equal((document.listeners.get("wheel")||[]).length,0); assert.equal((document.listeners.get("touchstart")||[]).length,0,"Initial fragment listeners do not persist after settlement");
  cleanup(); assert.equal(document.listenerCount, 0, "Initial fragment takeover listeners are temporary");
}

// Explorer selection is scoped and exact, keyboard activation has native-like
// semantics, journey steps are bounded, and comparison does not hide evidence.
{
  const document = new DocumentDouble(), root = append(document.body, "main");
  const a = fixtureExplorer(document, root), b = fixtureExplorer(document, root);
  const nested = fixtureExplorer(document, a.objects[0]);
  const cleanup = enhanceVisuals(root);
  assert.equal(a.nodes[0].getAttribute("role"), "button"); assert.equal(a.nodes[0].getAttribute("tabindex"), "0");
  assert.equal(a.drawing.getAttribute("role"), "group");
  assert.equal(a.previous.disabled, true); assert.equal(a.next.disabled, false);
  const enter = send(a.nodes[1], "keydown", { key: "Enter" }); assert.equal(enter.defaultPrevented, true);
  assert.equal(a.objects[1].open, true); assert.equal(a.objects[1].classList.contains("av-selected"), true); assert.equal(a.edge.classList.contains("av-related"), true);
  assert.equal(a.nodes[1].getAttribute("aria-pressed"), "true"); assert.equal(a.select.value, "object-1");
  assert.equal(document.activeElement, a.objects[1].querySelector("summary"));
  assert.equal(b.objects[1].open, false); assert.equal(nested.objects[1].open, false);
  click(a.next); assert.equal(a.objects[2].classList.contains("av-selected"), true); assert.equal(a.next.disabled, true); assert.equal(a.edge.classList.contains("av-related"), false);
  click(a.next); assert.equal(a.objects[0].classList.contains("av-selected"), false);
  click(a.previous); assert.equal(a.objects[1].classList.contains("av-selected"), true);
  a.select.value = "object-0"; send(a.select, "change"); assert.equal(a.objects[0].open, true); assert.equal(a.previous.disabled, true);
  const modifier = send(a.nodes[2], "keydown", { key: " ", ctrlKey: true }); assert.equal(modifier.defaultPrevented, false);
  const editor = append(a.nodes[2], "input"); assert.equal(send(editor, "keydown", { key: " " }).defaultPrevented, false);
  assert.equal(send(root, "keydown", { key: "g" }).defaultPrevented, false);
  const nativeButton = append(a.explorer, "button", { "data-av-inspect": "object-2" });
  assert.equal(send(nativeButton, "keydown", { key: "Enter" }).defaultPrevented, false); click(nativeButton); assert.equal(a.objects[2].open, true);
  a.compare[0].checked = true; send(a.compare[0], "change"); a.compare[2].checked = true; send(a.compare[2], "change");
  assert.equal(a.explorer.classList.contains("av-comparing"), true); assert.equal(a.objects[0].classList.contains("av-compared"), true); assert.equal(a.objects[2].classList.contains("av-compared"), true);
  for (const object of a.objects) assert.equal(object.hidden, false);
  assert.match(a.explorer.querySelector("[data-av-comparison-status]").textContent, /Unselected artifacts remain available/);
  a.compare[0].checked = false; send(a.compare[0], "change"); assert.equal(a.explorer.classList.contains("av-comparing"), false);
  cleanup(); assert.equal(a.nodes[0].getAttribute("role"), null); assert.equal(a.previous.disabled, false); assert.equal(a.objects[0].open, false);
  assert.equal(a.drawing.getAttribute("role"), "img"); assert.equal(a.select.value, ""); assert.equal(a.compare[2].checked, false);
  assert.equal(a.explorer.querySelector("[data-av-comparison-status]"), null); assert.equal(a.objects[2].classList.contains("av-selected"), false);
}

// A native selector may emit change for each arrow-key choice. Selection opens
// the original object and announces it without taking focus from the chooser.
{
  const document = new DocumentDouble(), root = append(document.body, "main");
  const explorer = fixtureExplorer(document, root), cleanup = enhanceVisuals(root);
  explorer.select.focus();
  for (const index of [1, 2, 0]) {
    explorer.select.value = `object-${index}`; send(explorer.select, "change");
    assert.equal(document.activeElement, explorer.select);
    assert.equal(explorer.objects[index].open, true);
    assert.equal(explorer.objects[index].classList.contains("av-selected"), true);
    assert.match(explorer.explorer.querySelector("[data-av-inspector-status]").textContent, new RegExp(`Object ${index}`));
  }
  click(explorer.nodes[2]); assert.equal(document.activeElement, explorer.objects[2].querySelector("summary"));
  cleanup(); assert.equal(explorer.select.value, "");
}

// Comparison groups selected live artifacts in supplied order. Changing the
// selection, leaving comparison and cleanup preserve all evidence and node state.
{
  const document = new DocumentDouble(), root = append(document.body, "main");
  const explorer = fixtureExplorer(document, root), sibling = fixtureExplorer(document, root);
  const grid = append(explorer.explorer, "div", { class: "av-deck-grid" });
  for (const object of explorer.objects) grid.appendChild(object);
  const note = append(grid, "p", {}, "Supplied trailing annotation");
  const original = [...grid.childNodes];
  const retainedInput = append(explorer.objects[2], "input", { value: "original" });
  const cleanup = enhanceVisuals(root);
  retainedInput.value = "reader state";
  // Selection order differs from supplied order; the presentation is not ranked.
  explorer.compare[2].checked = true; send(explorer.compare[2], "change");
  assert.deepEqual(grid.querySelectorAll("[data-av-object]"), explorer.objects);
  explorer.compare[0].checked = true; send(explorer.compare[0], "change");
  assert.deepEqual(grid.querySelectorAll("[data-av-object]"), [explorer.objects[0], explorer.objects[2], explorer.objects[1]]);
  assert.equal(explorer.objects[2].querySelector("input"), retainedInput); assert.equal(retainedInput.value, "reader state");
  assert.equal(grid.childNodes.at(-1), note);
  assert.deepEqual(sibling.explorer.querySelectorAll("[data-av-object]"), sibling.objects);
  explorer.compare[0].checked = false; explorer.compare[1].checked = true; send(explorer.compare[1], "change");
  assert.deepEqual(grid.querySelectorAll("[data-av-object]"), [explorer.objects[1], explorer.objects[2], explorer.objects[0]]);
  explorer.compare[2].checked = false; send(explorer.compare[2], "change");
  assert.deepEqual(grid.querySelectorAll("[data-av-object]"), explorer.objects);
  explorer.compare[0].checked = true; send(explorer.compare[0], "change");
  for (const [index, object] of explorer.objects.entries()) assert.equal(object.hidden, !explorer.compare[index].checked, "Only the chosen records occupy the fixed comparison area; original nodes remain recoverable");
  cleanup();
  assert.deepEqual(grid.childNodes, original);
  assert.equal(retainedInput.value, "reader state"); assert.equal(explorer.objects[0].open, false);
  assert.equal(explorer.explorer.querySelector("[data-av-comparison-status]"), null);
  const again = enhanceVisuals(root); again(); assert.deepEqual(grid.childNodes, original);
}

// Automatic fit and relative zoom retain exact evidence through the public enhancement.
{
  const document = new DocumentDouble(), root = append(document.body, "main"), frame = fixtureCard(document, root);
  frame.plot.remove();
  const view = viewportFixture(document, frame.card, { width: 900, height: 400, renderedWidth: 600, viewportWidth: 600, autoHeight: true });
  view.plot.setAttribute("data-av-content-view", "visual");
  const originalText = view.svg.textContent, cleanup = enhanceVisuals(root);
  assert.equal(view.minus.disabled, true); assert.equal(view.rect().width, 600);
  click(view.plus); assert.equal(view.rect().width, 750); assert.equal(view.plot.getAttribute("data-av-zoom"), "1.25");
  assert.match(view.plot.querySelector("[data-av-zoom-status]").textContent, /125%/);
  click(view.reset); assert.equal(view.rect().width, 600); assert.equal(view.reset.disabled, true); assert.equal(view.minus.disabled, true);
  assert.equal(view.svg.textContent, originalText); cleanup(); assert.equal(view.svg.getAttribute("style"), "color:blue");
}

// Fragments and search can reveal visual evidence after the reader chose data
// mode. Existing status DOM is restored rather than reconstructed on cleanup.
{
  const document = new DocumentDouble(), workspace = fixtureWorkspace(document, "with-plots");
  const frame = fixtureCard(document, workspace.second);
  const visualLabel = append(frame.svg, "text", { id: "unique-visual-target" }, "Unique plotted context");
  const sourceLink = append(workspace.first, "a", { href: "#unique-visual-target" }, "Plot context");
  const originalStatusChild = append(workspace.status, "em", {}, "Nested original status");
  const cleanup = enhanceVisuals(workspace.root);
  click(frame.card.querySelector('[data-av-view-toggle="data"]')); assert.equal(frame.plot.hidden, true);
  click(sourceLink); assert.equal(workspace.second.hidden, false); assert.equal(frame.plot.hidden, false); assert.equal(document.activeElement, visualLabel);
  click(frame.card.querySelector('[data-av-view-toggle="data"]'));
  workspace.search.value = "Unique plotted context"; send(workspace.search, "input"); assert.equal(frame.plot.hidden, true);
  click(workspace.root.querySelector("[data-av-search-hit]")); assert.equal(frame.plot.hidden, false);
  cleanup(); assert.equal(workspace.status.querySelector("em"), originalStatusChild);
}


function preferencePanel(document, parent) {
  const menu = append(parent, "details", { "data-av-settings": "", "data-av-script-only": "", hidden: "" });
  const summary = append(menu, "summary", {}, "Display"), controls = {};
  for (const [key, values] of Object.entries({ theme: ["system", "light", "dark"], spacing: ["comfortable", "compact"], sections: ["multiple", "solo"], palette: ["indigo", "ocean", "graphite", "aurora", "citrus", "rose", "custom"], canvas: ["ambient", "plain", "textured"], texture: ["grain", "grid"], intensity: ["low", "moderate"] })) {
    controls[key] = {};
    for (const value of values) controls[key][value] = append(menu, "input", { type: "radio", "data-av-setting": key, value });
  }
  const reset = append(menu, "button", { "data-av-reset-preferences": "" }, "Reset preferences");
  const status = append(menu, "output", { "data-av-preference-status": "" });
  const persistence = append(menu, "p", { "data-av-preference-persistence": "", hidden: "" });
  return { menu, summary, controls, reset, status, persistence };
}
function sectionFixture(document, parent, label, open = true) {
  const section = append(parent, "details", { class: "av-card", "data-av-section": "", ...(open ? { open: "" } : {}) });
  const summary = append(section, "summary"); append(summary, "h2", {}, label);
  const tools = append(section, "div", { "data-av-controls": "", hidden: "" });
  const focus = append(tools, "button", { "data-av-focus": "" }, "Inspect");
  const evidence = append(section, "p", {}, label + " original evidence and missingness");
  return { section, summary, focus, evidence };
}
function choose(panel, key, value) { const input = panel.controls[key][value]; input.checked = true; send(input, "change"); }

// Settings are scoped and do not change evidence, unrelated surfaces, or native
// supporting disclosures. Solo mode operates on peer sections, including nesting.
{
  const document = new DocumentDouble(), a = append(document.body, "main", { "data-av-preferences": "", "data-av-theme": "light" });
  const b = append(document.body, "main", { "data-av-preferences": "", "data-av-theme": "dark" });
  const pa = preferencePanel(document, a), pb = preferencePanel(document, b);
  const first = sectionFixture(document, a, "First"), second = sectionFixture(document, a, "Second");
  const supporting = append(first.section, "details", { open: "" }); append(supporting, "summary", {}, "Native data");
  const nestedOne = sectionFixture(document, first.section, "Nested one"), nestedTwo = sectionFixture(document, first.section, "Nested two");
  const other = sectionFixture(document, b, "Other surface");
  const fixed = append(a, "div", { "data-av-section-group": "", "data-av-section-mode": "multiple" });
  const fixedOne = sectionFixture(document, fixed, "Fixed one"), fixedTwo = sectionFixture(document, fixed, "Fixed two");
  const text = [first.evidence.textContent, second.evidence.textContent, other.evidence.textContent];
  const cleanup = enhanceVisuals(document.body);
  assert.equal(pa.menu.hidden, false); assert.equal(pa.controls.theme.light.checked, true); assert.equal(pb.controls.theme.dark.checked, true);
  choose(pa, "theme", "dark"); choose(pa, "spacing", "compact");
  assert.equal(a.getAttribute("data-av-theme"), "dark"); assert.equal(a.getAttribute("data-av-spacing"), "compact");
  assert.equal(b.getAttribute("data-av-theme"), "dark"); assert.equal(b.getAttribute("data-av-spacing"), "comfortable");
  choose(pa, "sections", "solo");
  assert.equal(first.section.open, true); assert.equal(second.section.open, false);
  assert.equal(nestedOne.section.open, true); assert.equal(nestedTwo.section.open, false);
  assert.equal(fixedOne.section.open, true); assert.equal(fixedTwo.section.open, true);
  nestedTwo.section.open = true; send(nestedTwo.section, "toggle", { bubbles: false });
  assert.equal(nestedOne.section.open, false); assert.equal(nestedTwo.section.open, true); assert.equal(first.section.open, true);
  second.section.open = true; send(second.section, "toggle", { bubbles: false });
  assert.equal(first.section.open, false); assert.equal(second.section.open, true); assert.equal(supporting.open, true); assert.equal(other.section.open, true);
  choose(pa, "sections", "multiple"); first.section.open = true; send(first.section, "toggle", { bubbles: false });
  assert.equal(second.section.open, true);
  assert.deepEqual([first.evidence.textContent, second.evidence.textContent, other.evidence.textContent], text);
  pa.menu.open = true; pa.controls.theme.light.focus(); send(pa.controls.theme.light, "keydown", { key: "Escape" });
  assert.equal(pa.menu.open, false); assert.equal(document.activeElement, pa.summary);
  pa.menu.open = true; click(other.evidence); assert.equal(pa.menu.open, false);
  click(pa.reset); assert.equal(a.getAttribute("data-av-theme"), "light"); assert.equal(a.getAttribute("data-av-spacing"), "comfortable");
  cleanup();
  assert.equal(a.getAttribute("data-av-theme"), "light"); assert.equal(a.hasAttribute("data-av-spacing"), false);
  assert.equal(first.section.open, true); assert.equal(second.section.open, true); assert.equal(nestedOne.section.open, true); assert.equal(nestedTwo.section.open, true);
  assert.equal(pa.menu.hidden, true); assert.equal(pa.menu.open, false);
}

// Opening policy remains effective across repeated section/full-report switches.
{
  const document = new DocumentDouble(), w = fixtureWorkspace(document, "mode-policy");
  w.root.setAttribute("data-av-preferences", "");
  const settings = preferencePanel(document, w.root);
  const a = sectionFixture(document, w.first, "First A"), b = sectionFixture(document, w.first, "First B"), c = sectionFixture(document, w.second, "Second C");
  const independent = append(w.second, "div", {"data-av-section-group":"", "data-av-section-mode":"multiple"});
  const d = sectionFixture(document, independent, "Lane D"), e = sectionFixture(document, independent, "Lane E");
  const cleanup = enhanceVisuals(w.root);
  const open = section => { section.section.open = true; send(section.section, "toggle", {bubbles:false}); };
  const single = w.root.querySelector("[data-av-show-single]");
  for (let round = 0; round < 3; round++) {
    choose(settings, "sections", "solo"); open(a); open(b); assert.equal(a.section.open, false);
    click(w.showAll); open(c); assert.equal(b.section.open, false); assert.equal(c.section.open, true);
    assert(d.section.open && e.section.open, "Explicit comparison groups keep their own ownership");
    open(a); assert.equal(c.section.open, false);
    choose(settings, "sections", "multiple"); open(b); open(c); assert(a.section.open && b.section.open && c.section.open);
    click(single); choose(settings, "sections", "solo"); open(a); assert.equal(b.section.open, false);
    click(w.secondNav); open(c); click(w.firstNav); open(b); assert.equal(a.section.open, false);
  }
  cleanup(); assert.equal(w.root.getAttribute("data-av-reader-mode"), null);
}

// Native frames used as the hydration root stay separate from their child group;
// dialog inspection keeps the same appearance, spacing and solo behavior.
{
  const document = new DocumentDouble(), outer = sectionFixture(document, document.body, "Outer");
  outer.section.setAttribute("data-av-preferences", ""); outer.section.setAttribute("data-av-theme", "dark"); outer.section.setAttribute("data-av-spacing", "compact"); outer.section.setAttribute("data-av-sections", "solo");
  const panel = preferencePanel(document, outer.section);
  const first = sectionFixture(document, outer.section, "First child"), second = sectionFixture(document, outer.section, "Second child");
  const cleanup = enhanceVisuals(outer.section);
  assert.equal(outer.section.open, true); assert.equal(first.section.open, true); assert.equal(second.section.open, false);
  second.section.open = true; send(second.section, "toggle", { bubbles: false });
  assert.equal(outer.section.open, true); assert.equal(first.section.open, false);
  click(second.focus);
  const dialog = document.body.querySelector("dialog");
  assert.equal(dialog.getAttribute("data-av-theme"), "dark"); assert.equal(dialog.getAttribute("data-av-spacing"), "compact");
  choose(panel, "theme", "light"); assert.equal(dialog.getAttribute("data-av-theme"), "light");
  cleanup(); document.flush(); assert.equal(first.section.open, true); assert.equal(second.section.open, true); assert.equal(outer.section.open, true);
  assert.equal(document.body.querySelector("dialog"), null);
}

// If a reader folds a focused frame, closing inspection returns to its visible
// summary rather than attempting to focus a control inside the closed section.
{
  const document = new DocumentDouble(), root = append(document.body, "main");
  const frame = sectionFixture(document, root, "Collapsible inspection"), cleanup = enhanceVisuals(root);
  click(frame.focus); frame.section.open = false; send(frame.section, "toggle", { bubbles: false });
  click(root.querySelector("[data-av-close-focus]"));
  assert.equal(frame.section.open, false); assert.equal(document.activeElement, frame.summary);
  cleanup(); assert.equal(frame.section.open, true);
}

// Typed preference persistence migrates recognized legacy choices without changing
// their original bytes, and applies current-page choices when persistence fails.
{
  const document = new DocumentDouble();
  const legacy = JSON.stringify({ theme: "dark", spacing: "compact", sections: "solo" });
  const store = fixtureStorage(document, [["this-report", legacy], ["unrelated", "untouched"]]);
  const root = append(document.body, "main", { id: "display-report", "data-av-preferences": "", "data-av-storage-key": "this-report", "data-av-theme": "light" });
  const panel = preferencePanel(document, root), first = sectionFixture(document, root, "A"), second = sectionFixture(document, root, "B");
  const cleanup = enhanceVisuals(root); await cleanup.whenIdle();
  assert.equal(root.getAttribute("data-av-theme"), "dark"); assert.equal(root.getAttribute("data-av-spacing"), "compact"); assert.equal(second.section.open, false);
  assert.equal(databaseWrites(store), 0, "Loading preferences must not initialize or rewrite storage");
  choose(panel, "theme", "system"); await cleanup.whenIdle();
  const record = stored(store, "this-report");
  assert.deepEqual(record.owner, { kind: "preferences", reportId: "display-report", revision: "1" });
  assert.deepEqual(record.value, { theme: "system", spacing: "compact", sections: "solo", palette: "indigo", canvas: "ambient", texture: "grain", intensity: "low" });
  assert.equal(databaseWrites(store), 1); assert.equal(store.legacy.get("this-report"), legacy); assert.equal(store.legacy.get("unrelated"), "untouched"); assert.deepEqual(store.writes, []);
  cleanup(); assert.equal(root.getAttribute("data-av-theme"), "light"); assert.equal(first.section.open, true); assert.equal(second.section.open, true);
  const unavailable = indexedDBDouble(); unavailable.failOpen = true; document.defaultView.indexedDB = unavailable;
  Object.defineProperty(document.defaultView, "localStorage", { get() { throw new Error("Storage denied"); } });
  const again = enhanceVisuals(root); await again.whenIdle(); choose(panel, "theme", "dark"); await again.whenIdle();
  assert.equal(root.getAttribute("data-av-theme"), "dark"); assert.match(panel.persistence.textContent, /session|unavailable/); assert.equal(panel.persistence.hidden, false); assert.deepEqual(store.indexedDB.records.get("this-report"), record); again();
}
// An unknown legacy field is now an ownership/schema refusal, not permission to
// replace arbitrary data that merely happens to contain a known theme property.
{
  const document = new DocumentDouble(), legacy = JSON.stringify({theme:"dark",unrelated:"protected"});
  const store = fixtureStorage(document, [["mixed",legacy]]);
  const root = append(document.body, "section", {id:"mixed-format", "data-av-preferences":"", "data-av-theme":"light", "data-av-storage-key":"mixed"});
  const panel = preferencePanel(document,root), cleanup = enhanceVisuals(root); await cleanup.whenIdle();
  assert.equal(root.getAttribute("data-av-theme"),"light"); choose(panel,"theme","dark"); await cleanup.whenIdle();
  assert.equal(root.getAttribute("data-av-theme"),"dark"); assert.match(panel.persistence.textContent,/protected/); assert.equal(store.indexedDB.records.size,0); assert.equal(store.legacy.get("mixed"),legacy); cleanup();
}

// Revealing linked/search evidence in solo mode opens the requested section,
// closes only its peers and retains every original object in the document.
{
  const document = new DocumentDouble(), workspace = fixtureWorkspace(document, "solo-search");
  workspace.root.setAttribute("data-av-preferences", ""); workspace.root.setAttribute("data-av-sections", "solo");
  const a = sectionFixture(document, workspace.first, "Earlier"), b = sectionFixture(document, workspace.first, "Later");
  b.evidence.id = "linked-section-evidence";
  const link = append(workspace.second, "a", { href: "#linked-section-evidence" }, "Original grounds");
  const cleanup = enhanceVisuals(workspace.root);
  assert.equal(a.section.open, true); assert.equal(b.section.open, false);
  click(link); assert.equal(b.section.open, true); assert.equal(a.section.open, false); assert.equal(document.getElementById("linked-section-evidence"), b.evidence);
  workspace.search.value = "Earlier original evidence"; send(workspace.search, "input");
  assert.equal(a.section.open, false); assert.equal(b.section.open, true);
  click(workspace.root.querySelector("[data-av-search-hit]"));
  assert.equal(a.section.open, true); assert.equal(b.section.open, false); assert.equal(workspace.first.hidden, false);
  cleanup(); assert.equal(a.section.open, true); assert.equal(b.section.open, true);
}



// A noncollapsible frame keeps its original surface when a common enhancement
// root moves it to inspection; reset inside a moved frame keeps that same owner.
{
  const document = new DocumentDouble(), store = fixtureStorage(document);
  const root = append(document.body, "main", { id:"outer-surface", "data-av-preferences": "", "data-av-theme": "light", "data-av-storage-key": "outer-report" });
  const inner = append(root, "div", { id:"inner-surface", "data-av-preferences": "", "data-av-theme": "dark", "data-av-spacing": "compact", "data-av-storage-key": "inner-snippet" });
  const plain = fixtureCard(document, inner, "ordinary-frame");
  const section = sectionFixture(document, inner, "Settings inside a section"), panel = preferencePanel(document, section.section);
  const cleanup = enhanceVisuals(root);
  click(plain.focus);
  const dialog = root.querySelector("dialog");
  assert.equal(dialog.getAttribute("data-av-theme"), "dark"); assert.equal(dialog.getAttribute("data-av-spacing"), "compact");
  click(dialog.querySelector("[data-av-close-focus]"));
  choose(panel, "theme", "light"); assert.equal(inner.getAttribute("data-av-theme"), "light"); await cleanup.whenIdle(); const beforeReset=databaseWrites(store);
  click(section.focus); click(panel.reset);
  assert.equal(inner.getAttribute("data-av-theme"), "dark"); assert.equal(inner.getAttribute("data-av-spacing"), "compact");
  assert.equal(root.getAttribute("data-av-theme"), "light"); assert.equal(root.getAttribute("data-av-spacing"), "comfortable");
  await cleanup.whenIdle(); assert.equal(databaseWrites(store),beforeReset+1); assert.equal(store.indexedDB.records.has("outer-report"),false);
  assert.deepEqual(stored(store,"inner-snippet").owner,{kind:"preferences",reportId:"inner-surface",revision:"1"}); assert.equal(stored(store,"inner-snippet").value.theme,"dark"); assert.deepEqual(store.writes,[]);
  assert.equal(dialog.getAttribute("data-av-theme"), "dark");
  cleanup(); document.flush(); assert.equal(plain.card.parentNode, inner); assert.equal(section.section.parentNode, inner);
}

// Entering solo mode retains the initiating section and its original ancestor
// path, including when inspection has temporarily moved it away from that path.
for (const inspectFirst of [false, true]) {
  const document = new DocumentDouble(), root = append(document.body, "main", { "data-av-preferences": "" });
  const earlier = sectionFixture(document, root, "Earlier parent"), current = sectionFixture(document, root, "Current parent");
  const firstChild = sectionFixture(document, current.section, "Earlier child"), currentChild = sectionFixture(document, current.section, "Current child");
  const panel = preferencePanel(document, currentChild.section), cleanup = enhanceVisuals(root);
  if (inspectFirst) click(currentChild.focus);
  panel.menu.open = true; panel.controls.sections.solo.focus(); choose(panel, "sections", "solo");
  assert.equal(earlier.section.open, false); assert.equal(current.section.open, true);
  assert.equal(firstChild.section.open, false); assert.equal(currentChild.section.open, true);
  assert.equal(document.activeElement, panel.controls.sections.solo); assert.equal(panel.menu.open, true);
  if (inspectFirst) {
    click(root.querySelector("[data-av-close-focus]"));
    assert.equal(currentChild.section.parentNode, current.section); assert.equal(current.section.open, true);
  }
  cleanup(); document.flush();
  for (const item of [earlier, current, firstChild, currentChild]) assert.equal(item.section.open, true);
}

// Native disclosure state, selector state and highlighted marks agree. Explicit
// comparisons remain open in solo mode, and an empty selection starts at item one.
{
  const document = new DocumentDouble(), root = append(document.body, "main", { "data-av-preferences": "", "data-av-sections": "solo" });
  const a = fixtureExplorer(document, root), panel = preferencePanel(document, root);
  const cleanup = enhanceVisuals(root);
  click(a.next); assert.equal(a.objects[0].open, true); assert.equal(a.select.value, "object-0");
  a.objects[1].open = true; send(a.objects[1], "toggle", { bubbles: false });
  assert.equal(a.objects[0].open, false); assert.equal(a.select.value, "object-1");
  assert.equal(a.nodes[0].getAttribute("aria-pressed"), "false"); assert.equal(a.nodes[1].getAttribute("aria-pressed"), "true");
  a.objects[1].open = false; send(a.objects[1], "toggle", { bubbles: false }); assert.equal(a.select.value, "");
  for (const index of [0, 2]) { a.compare[index].checked = true; send(a.compare[index], "change"); }
  send(a.objects[0], "toggle", { bubbles: false }); send(a.objects[2], "toggle", { bubbles: false });
  assert.equal(a.objects[0].open, true); assert.equal(a.objects[2].open, true);
  a.compare[0].checked = false; send(a.compare[0], "change"); assert.equal(a.objects[2].open, true); assert.equal(a.objects[0].open, false);
  choose(panel, "palette", "ocean"); choose(panel, "canvas", "plain");
  assert.equal(root.getAttribute("data-av-palette"), "ocean"); assert.equal(root.getAttribute("data-av-canvas"), "plain");
  cleanup(); assert.equal(root.hasAttribute("data-av-palette"), false);
}

// Approved reading paths navigate only declared views. Awaited hydration restores
// without logging a navigation; explicit report fragments are real entry choices.
for (const explicit of [false, true]) {
  const document = new DocumentDouble(), w = fixtureWorkspace(document, "route-report");
  const route = append(w.root, "nav", { "data-av-journey-id": "reader", "data-av-journey-label": "Read the evidence", "data-av-journey-steps": '["start","exceptions"]', hidden: "" });
  append(route, "output", { "data-av-path-position": "" });
  const previous = append(route, "button", { "data-av-path-step": "-1" });
  const next = append(route, "button", { "data-av-path-step": "1" });
  const leave = append(route, "button", { "data-av-path-exit": "" });
  const begin = append(w.root, "a", { "data-av-start-journey": "reader", href: "#route-report--view-start" });
  const notebook = append(w.root, "details", { id: "route-notebook", "data-av-notebook": "", "data-av-notebook-scope": "route-report", "data-av-notebook-revision": "v1", "data-av-notebook-storage-key": "reader-test" });
  append(notebook, "summary", {}, "Your notebook");
  const state = { version: 1, reportId: "route-report", revision: "v1", viewId: "exceptions", mode: "all", journeyId: "reader", bookmarks: [], notes: [], activity: [], droppedActivityCount: 0, nextSequence: 1 };
  const legacy = JSON.stringify(state), store = fixtureStorage(document, [["reader-test",legacy]]);
  if (explicit) document.defaultView.location.hash = "#route-report--view-start";
  const cleanup = enhanceVisuals(w.root); await cleanup.whenIdle();
  assert.equal(w.second.hidden, explicit, notebook.textContent); assert.equal(w.first.hidden, false);
  if (!explicit) assert.equal(databaseWrites(store), 0, "Restoring the saved view is not a new reader action");
  else assert.equal(stored(store,"reader-test").value.state.viewId,"start");
  click(begin); assert.equal(route.hidden, false); assert.equal(previous.disabled, true); assert.equal(next.disabled, false);
  click(next); assert.equal(w.first.hidden, true); assert.equal(w.second.hidden, false); assert.equal(next.disabled, true); await cleanup.whenIdle();
  const count = databaseWrites(store);
  w.search.value = "deadlock"; send(w.search, "input"); await cleanup.whenIdle(); assert.equal(databaseWrites(store), count);
  click(w.showAll); assert.equal(route.hidden, true); await cleanup.whenIdle(); assert.equal(stored(store,"reader-test").value.state.viewId, "exceptions"); assert.equal(stored(store,"reader-test").value.state.mode,"all");
  click(w.root.querySelector("[data-av-show-single]")); assert.equal(route.hidden, false); assert.equal(w.first.hidden, true);
  click(leave); assert.equal(route.hidden, true); await cleanup.whenIdle(); assert.equal(stored(store,"reader-test").value.state.journeyId, null);
  assert.equal(store.legacy.get("reader-test"),legacy); assert.deepEqual(store.writes,[]);
  assert.deepEqual(stored(store,"reader-test").owner,{kind:"notebook",reportId:"route-report",revision:"v1"});
  cleanup(); assert.equal(notebook.querySelector("[data-av-notebook-note]"), null);
}

// Local inspection keeps the reader's full-report choice while remembering the
// most recently used section. Explicit view navigation is still a section choice.
{
  const document = new DocumentDouble(), w = fixtureWorkspace(document, "full-reading");
  const explorer = fixtureExplorer(document, w.second);
  const cleanup = enhanceVisuals(w.root);
  click(w.showAll); click(explorer.nodes[0]);
  assert.equal(w.first.hidden, false); assert.equal(w.second.hidden, false); assert.equal(w.showAll.getAttribute("aria-pressed"), "true");
  explorer.select.value = "object-1"; send(explorer.select, "change");
  assert.equal(w.first.hidden, false); assert.equal(w.showAll.getAttribute("aria-pressed"), "true");
  click(w.root.querySelector("[data-av-show-single]")); assert.equal(w.first.hidden, true); assert.equal(w.second.hidden, false);
  click(w.showAll); click(w.firstNav); assert.equal(w.first.hidden, false); assert.equal(w.second.hidden, true);
  cleanup();
}

// Same-document key conflicts are rejected before any storage access.
{
  const document = new DocumentDouble(), w = fixtureWorkspace(document, "conflict"), store=fixtureStorage(document,[["shared","Prior notebook bytes"]]);
  w.root.setAttribute("data-av-preferences", ""); w.root.setAttribute("data-av-storage-key", "shared");
  const controls = preferencePanel(document, w.root);
  const notebook = append(w.root, "details", { id: "conflict-book", "data-av-notebook": "", "data-av-notebook-scope": "conflict", "data-av-notebook-revision": "v1", "data-av-notebook-storage-key": "shared" });
  append(notebook, "summary", {}, "Notebook");
  let reads=0; document.defaultView.localStorage.getItem=()=>{reads++;throw new Error("Conflicting data must not be read");};
  const cleanup = enhanceVisuals(w.root); choose(controls, "theme", "dark"); await cleanup.whenIdle();
  assert.match(notebook.textContent, /different storage keys/); assert.equal(reads,0); assert.deepEqual(store.indexedDB.calls,[]); assert.equal(store.legacy.get("shared"),"Prior notebook bytes");
  assert.equal(w.root.getAttribute("data-av-theme"), "dark"); cleanup();
}

// Opening a utility animates its panel, never the positioning ancestor whose
// transform would temporarily constrain an absolute popover to the trigger width.
{
  const document = new DocumentDouble(), root = append(document.body, "main");
  for (const [attribute, className] of [["data-av-notebook", "av-notebook-popover"], ["data-av-settings", "av-settings-panel"]]) {
    const menu = append(root, "details", { [attribute]: "" }); append(menu, "summary", {}, "Open utility");
    const panel = append(menu, "div", { class: className });
    menu.animate = () => { throw new Error("Do not transform the positioning ancestor"); };
    const cleanup = enhanceVisuals(root); menu.open = true; send(menu, "toggle", { bubbles: false });
    assert.equal(document.animations.length > 0, true); cleanup(); menu.remove();
  }
}

// Custom theme controls share their scope with presets, save only valid colors,
// follow a moved frame into expansion, and restore the author defaults on reset.
{
  const document = new DocumentDouble(), root = append(document.body, "main", { id: "custom-theme", "data-av-preferences": "", "data-av-palette": "custom", "data-av-custom-colors": '{"main":"#112233","secondary":"#445566","tertiary":"#778899"}', "data-av-storage-key": "colors-only" });
  const store = fixtureStorage(document);
  const settings = preferencePanel(document, root), colorInput = append(settings.menu, "input", { type: "color", "data-av-color": "main" });
  const editor = append(settings.menu, "fieldset", { "data-av-custom-editor": "", hidden: "" });
  const preview = append(settings.menu, "label", { "data-av-palette": "custom" });
  const frame = fixtureCard(document, root), cleanup = enhanceVisuals(root); await cleanup.whenIdle();
  assert.equal(root.style.getPropertyValue("--av-brand-main"), "#112233"); assert.equal(editor.hidden, false);
  colorInput.value = "#e1c2a3"; send(colorInput, "change");
  await cleanup.whenIdle(); assert.deepEqual(stored(store,"colors-only").owner,{kind:"preferences",reportId:"custom-theme",revision:"1"}); assert.equal(stored(store,"colors-only").value.customColors.main, "#e1c2a3");
  click(frame.focus); const dialog = root.querySelector("dialog"); assert.equal(dialog.style.getPropertyValue("--av-brand-main"), "#e1c2a3");
  choose(settings, "palette", "aurora"); assert.equal(root.style.getPropertyValue("--av-brand-main"), ""); assert.equal(editor.hidden, true);
  assert.equal(preview.style.getPropertyValue("--av-brand-main"), "#e1c2a3", "The custom preview must retain its saved colors while another preset is active");
  choose(settings, "palette", "custom"); assert.equal(root.style.getPropertyValue("--av-brand-main"), "#e1c2a3");
  assert.equal(dialog.style.getPropertyValue("--av-brand-tertiary"), "#778899");
  await cleanup.whenIdle(); colorInput.value = 'red; background:url(https://invalid.example)'; const count = databaseWrites(store); send(colorInput, "change"); await cleanup.whenIdle(); assert.equal(databaseWrites(store), count);
  click(settings.reset); assert.equal(root.style.getPropertyValue("--av-brand-main"), "#112233"); await cleanup.whenIdle(); assert.equal(stored(store,"colors-only").value.customColors.main,"#112233"); assert.deepEqual(store.writes,[]);
  cleanup(); assert.equal(root.hasAttribute("style"), false);
}

// The opening task/context and report notes are part of report-wide search.
// Returning to either original surface clears the overlay without losing mode.
{
  const document = new DocumentDouble(), w = fixtureWorkspace(document, "opening-search");
  const intro = append(w.root, "div", { class: "av-workspace-heading" }); append(intro, "h1", {}, "Coastal observation task");
  const brief = append(w.root, "section", { class: "av-report-brief" }); append(brief, "h2", {}, "Which option works with the accelerator permit?");
  const duplicate = append(w.first, "p", { "data-av-view-question": "" }, "Which option works with the accelerator permit?");
  const hiddenCondition = append(brief, "details"); append(hiddenCondition, "summary", {}, "Operating limits"); append(hiddenCondition, "p", {}, "A fallback battery reserve is required.");
  const framedCondition = sectionFixture(document, brief, "Transfer condition", false); framedCondition.evidence.textContent = "The transfer needs local image copies.";
  const hiddenFootnote = append(w.footer, "details"); append(hiddenFootnote, "summary", {}, "Evidence scope"); append(hiddenFootnote, "p", {}, "The retained traverse sample is narrow.");
  const cleanup = enhanceVisuals(w.root); click(w.showAll);
  for (const [query, target] of [["accelerator permit", brief], ["coastal observation", intro], ["provenance", w.footer.querySelector("p")]]) {
    w.search.value = query; send(w.search, "input");
    assert.equal(w.root.querySelectorAll("[data-av-search-hit]").length, 1);
    click(w.root.querySelector("[data-av-search-hit]"));
    assert.equal(w.search.value, ""); assert.equal(w.root.querySelector("[data-av-search-results]").hidden, true);
    assert.equal(w.showAll.getAttribute("aria-pressed"), "true"); assert.equal(document.activeElement, target);
  }
  for (const [query, target] of [["fallback battery reserve", hiddenCondition], ["traverse sample", hiddenFootnote], ["local image copies", framedCondition.section]]) {
    w.search.value = query; send(w.search, "input");
    assert.equal(target.open, false);
    click(w.root.querySelector("[data-av-search-hit]"));
    assert.equal(target.open, true); assert(target.contains(document.activeElement));
    assert.equal(w.root.querySelector("[data-av-search-results]").hidden, true);
    assert.equal(w.showAll.getAttribute("aria-pressed"), "true");
  }
  cleanup();
}

// Invalid full-shell nesting is rejected before any markup, listener or storage
// mutation. Nested sections/surfaces remain permitted by the other cases above.
{
  const document = new DocumentDouble(), outer = fixtureWorkspace(document,"outer-shell"), inner = fixtureWorkspace(document,"inner-shell"), store = fixtureStorage(document);
  outer.second.appendChild(inner.root);
  const card = fixtureCard(document, inner.first), settings = preferencePanel(document, outer.root);
  outer.root.setAttribute("data-av-preferences",""); outer.root.setAttribute("data-av-storage-key","do-not-open");
  const before = document.body.textContent, descendants = [...document.body.querySelectorAll("[id]")];
  for (const root of [outer.root,inner.root]) assert.throws(()=>enhanceVisuals(root),/one workspace shell/);
  assert.equal(document.body.textContent,before); assert.deepEqual(document.body.querySelectorAll("[id]"),descendants);
  assert.equal(outer.root.hasAttribute("data-av-enhanced"),false); assert.equal(inner.root.hasAttribute("data-av-enhanced"),false);
  assert.equal(card.tools.hidden,true); assert.equal(settings.menu.hidden,true); assert.equal(outer.second.hidden,false); assert.equal(inner.second.hidden,false);
  assert.equal(document.body.querySelector("dialog"),null); assert.equal(document.body.querySelector("[data-av-view-toggle]"),null);
  assert.equal(document.listenerCount,0); assert.equal(document.defaultView.listenerCount,0); assert.equal(document.defaultView.media.listenerCount,0); assert.deepEqual(store.indexedDB.calls,[]);
}

// A shared enhancement root may own sibling report regions. Navigation/search,
// display ownership and disposal of those regions remain independent.
{
  const document = new DocumentDouble(), a=fixtureWorkspace(document,"sibling-a"), b=fixtureWorkspace(document,"sibling-b"), store=fixtureStorage(document);
  for (const report of [a,b]) { report.root.setAttribute("data-av-preferences",""); report.root.setAttribute("data-av-storage-key",report.root.id+"-display"); }
  const pa=preferencePanel(document,a.root), pb=preferencePanel(document,b.root), cleanup=enhanceVisuals(document.body); await cleanup.whenIdle();
  click(a.showAll); assert.equal(a.second.hidden,false); assert.equal(b.second.hidden,true);
  choose(pa,"palette","ocean"); choose(pb,"theme","dark"); await cleanup.whenIdle();
  assert.equal(a.root.getAttribute("data-av-palette"),"ocean"); assert.equal(b.root.getAttribute("data-av-palette"),"indigo"); assert.equal(a.root.getAttribute("data-av-theme"),"system");
  assert.deepEqual(stored(store,"sibling-a-display").owner,{kind:"preferences",reportId:"sibling-a",revision:"1"});
  assert.deepEqual(stored(store,"sibling-b-display").owner,{kind:"preferences",reportId:"sibling-b",revision:"1"});
  b.search.value="deadlock"; send(b.search,"input"); assert.equal(a.root.querySelectorAll("[data-av-search-hit]").length,0); assert.equal(b.root.querySelectorAll("[data-av-search-hit]").length,1);
  click(b.root.querySelector("[data-av-search-hit]")); assert.equal(b.second.hidden,false); assert.equal(b.first.hidden,true); assert.equal(a.first.hidden,false); assert.equal(a.second.hidden,false); assert.equal(a.showAll.getAttribute("aria-pressed"),"true");
  cleanup(); assert.equal(a.second.hidden,false); assert.equal(b.second.hidden,false); assert.equal(a.searchArea.hidden,true); assert.equal(b.searchArea.hidden,true); assert.equal(document.listenerCount,0); assert.equal(document.defaultView.listenerCount,0);
}

// Canvas controls stay adjacent to their own drawing. Their original plot
// owners survive nested sections, data mode and expanded inspection.
{
  const document=new DocumentDouble(), root=append(document.body,"main"), outer=fixtureCard(document,root,"bar-outer"), inner=fixtureCard(document,outer.card,"bar-inner");
  outer.plot.remove(); inner.plot.remove(); outer.tools.className="av-frame-tools"; inner.tools.className="av-frame-tools";
  const a=viewportFixture(document,outer.card,{width:900,renderedWidth:900}), b=viewportFixture(document,inner.card,{width:600,renderedWidth:600});
  for (const view of [a,b]) { view.plot.setAttribute("data-av-content-view","visual"); view.toolbar.className="av-plot-toolbar"; }
  const aParent=a.toolbar.parentNode, bParent=b.toolbar.parentNode, cleanup=enhanceVisuals(root);
  assert(a.toolbar.parentNode===aParent); assert(b.toolbar.parentNode===bParent); assert(a.plus.closest("[data-av-plot]")===a.plot);
  click(a.plus); assert.equal(a.rect().width,a.viewport.clientWidth*1.25); assert.equal(b.rect().width,b.viewport.clientWidth);
  click(outer.focus); const dialog=root.querySelector("dialog"); assert.equal(dialog.open,true);
  click(a.fit); assert.equal(a.rect().width,a.viewport.clientWidth); assert.equal(b.rect().width,b.viewport.clientWidth);
  click(b.plus); assert.equal(b.rect().width,b.viewport.clientWidth*1.25); assert.equal(a.rect().width,a.viewport.clientWidth);
  const outerData=outer.tools.querySelector('[data-av-view-toggle="data"]'); click(outerData); assert.equal(a.plot.hidden,true); assert.equal(b.plot.hidden,false);
  click(outer.tools.querySelector('[data-av-view-toggle="visual"]')); click(a.actual); assert.equal(a.rect().width,900); assert.equal(b.rect().width,b.viewport.clientWidth*1.25);
  click(dialog.querySelector("[data-av-close-focus]")); assert.equal(outer.card.parentNode,root); assert(a.toolbar.parentNode===aParent);
  cleanup(); document.flush(); assert.equal(a.toolbar.parentNode,aParent); assert.equal(b.toolbar.parentNode,bParent); assert.equal(a.svg.getAttribute("style"),"color:blue"); assert.equal(b.svg.getAttribute("style"),"color:blue");
}

// Pending notebook/theme reads cannot restore stale state over reader actions,
// and cleanup must prevent late UI mutations even after storage completes.
for (const disposeEarly of [false,true]) {
  const document=new DocumentDouble(), w=fixtureWorkspace(document,disposeEarly?"late-dispose":"late-edit"), factory=indexedDBDouble(); factory.paused=true;
  w.root.setAttribute("data-av-preferences",""); w.root.setAttribute("data-av-storage-key","late-display"); const settings=preferencePanel(document,w.root);
  const book=append(w.root,"details",{id:w.root.id+"-book","data-av-notebook":"","data-av-notebook-scope":w.root.id,"data-av-notebook-revision":"v1","data-av-notebook-storage-key":"late-reader"}); append(book,"summary",{},"Notebook");
  const state={version:1,reportId:w.root.id,revision:"v1",viewId:"exceptions",mode:"all",journeyId:null,bookmarks:[],notes:[],activity:[],droppedActivityCount:0,nextSequence:1};
  const legacy=JSON.stringify(state),store=fixtureStorage(document,[["late-reader",legacy],["late-display",JSON.stringify({theme:"dark"})]],factory),cleanup=enhanceVisuals(w.root);
  assert.equal(w.second.hidden,true);
  if (disposeEarly) {
    cleanup(); const before=w.root.textContent, focusBefore=document.activeElement;
    factory.resume(); await cleanup.whenIdle(); await new Promise(resolve=>setImmediate(resolve)); await new Promise(resolve=>setImmediate(resolve));
    assert.equal(w.root.textContent,before); assert.equal(document.activeElement,focusBefore); assert.equal(book.querySelector("[data-av-notebook-note]"),null); assert.equal(w.root.hasAttribute("data-av-theme"),false); assert.equal(w.second.hidden,false); assert.equal(databaseWrites(store),0);
  } else {
    choose(settings,"theme","light"); click(w.firstNav); factory.resume(); await cleanup.whenIdle();
    assert.equal(w.root.getAttribute("data-av-theme"),"light"); assert.equal(w.first.hidden,false); assert.equal(w.second.hidden,true); assert.equal(stored(store,"late-reader").value.state.viewId,"start"); assert.equal(stored(store,"late-display").value.theme,"light"); cleanup();
  }
  assert.equal(store.legacy.get("late-reader"),legacy); assert.deepEqual(store.writes,[]);
}

console.log("interaction source contracts passed (DOM/transaction/geometry doubles only; native browser behavior unverified)");

})().catch(error => { console.error(error); process.exitCode = 1; });
