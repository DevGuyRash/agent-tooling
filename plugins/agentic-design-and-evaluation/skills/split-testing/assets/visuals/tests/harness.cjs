// Loads the built browser bundle (dist/agentic-visuals.js) into an isolated
// node:vm context and runs named cases. The renderers are pure string
// functions, so most cases need no DOM; the few that exercise browser behavior
// use the small stubs below. A case script prints one JSON line of results,
// which test_rendering.py turns into one subtest per case.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const VISUALS = path.resolve(__dirname, "..");
const BUNDLE = path.join(VISUALS, "dist", "agentic-visuals.js");
let script;

/** A fresh AgenticVisuals global. `globals` seeds the context (for example a
 * stub `document`, which makes the bundle auto-mount as it loads). */
function loadVisuals(globals = {}) {
  script ||= new vm.Script(fs.readFileSync(BUNDLE, "utf8"), { filename: BUNDLE });
  const context = vm.createContext({ console, ...globals });
  script.runInContext(context);
  if (!context.AgenticVisuals) throw new Error("dist/agentic-visuals.js did not define AgenticVisuals");
  return context.AgenticVisuals;
}

/** Values created inside the vm realm have foreign prototypes; compare plain copies. */
const plain = value => JSON.parse(JSON.stringify(value));

// ------------------------------------------------------------------ cases

const results = [];
function run(name, fn, defect) {
  try { fn(); return { name, defect, error: null }; }
  catch (error) { return { name, defect, error: error instanceof Error ? error.message : String(error) }; }
}
/** A behavior the library must have. */
function test(name, fn) { results.push(run(name, fn, false)); }
/** A known library defect: expected to fail until the library is fixed, at
 * which point the Python side asks for the case to become an ordinary test. */
test.defect = (name, fn) => { results.push(run(name, fn, true)); };
function report() { process.stdout.write(JSON.stringify(results) + "\n"); }

// ------------------------------------------------------------------ assertions

function fail(message) { throw new Error(message); }
function snippet(html, needle, radius = 120) {
  const at = html.indexOf(needle);
  return at < 0 ? "" : html.slice(Math.max(0, at - radius), at + needle.length + radius);
}
function includes(html, needle, what = needle) {
  if (!html.includes(needle)) fail(`expected ${what} in the output`);
}
function excludes(html, needle, what = needle) {
  if (html.includes(needle)) fail(`unexpected ${what} in the output: …${snippet(html, needle)}…`);
}
function equal(actual, expected, what) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a !== e) fail(`${what}: expected ${e}, got ${a}`);
}
function ok(value, what) { if (!value) fail(what); }
function count(html, needle) { return html.split(needle).length - 1; }
function throws(fn, pattern, what) {
  try { fn(); } catch (error) {
    if (pattern && !pattern.test(String(error && error.message))) fail(`${what}: wrong error "${error && error.message}"`);
    return;
  }
  fail(`${what}: expected an error`);
}

/** The markup of the element that opens at `marker`, through its matching close.
 * Enough for the library's own well-formed output; not a general HTML parser. */
function element(html, marker) {
  const start = html.indexOf(marker);
  if (start < 0) fail(`no element matching ${marker}`);
  const open = html.lastIndexOf("<", start);
  const tag = /^<([a-z0-9-]+)/i.exec(html.slice(open))[1];
  const re = new RegExp(`<(/?)${tag}(?=[\\s>/])`, "gi");
  re.lastIndex = open;
  let depth = 0, m;
  while ((m = re.exec(html))) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) return html.slice(open, html.indexOf(">", m.index) + 1);
  }
  fail(`unclosed element at ${marker}`);
}

/** Section ids of a rendered report, in order. */
function sectionIds(html) {
  return [...html.matchAll(/<section class="av-section" id="([^"]+)"/g)].map(m => m[1]);
}

// ------------------------------------------------------------------ browser stubs

/** Enhance a rendered report with a minimal element stub and return a function
 * that opens the run drawer for run i and returns the drawer's markup. Only the
 * paths enhance() takes for a report without ledger, index or diagrams are stubbed. */
function drawerOpener(V, spec) {
  const listeners = {};
  const body = { innerHTML: "" };
  const win = { Event: class { constructor(type) { this.type = type; } }, addEventListener() {}, removeEventListener() {}, scrollY: 0 };
  const doc = { defaultView: win, dispatchEvent() { return true; } };
  const dialog = {
    open: false, contains: () => false, showModal() { this.open = true; }, setAttribute() {}, addEventListener() {}, removeEventListener() {},
    querySelector: selector => selector === "[data-av-drawer-body]" ? body : null,
  };
  const report = {
    ownerDocument: doc, matches: selector => selector === "[data-av-report]",
    querySelector: selector => selector === "[data-av-drawer]" ? dialog : null, querySelectorAll: () => [],
    addEventListener: (type, fn) => { listeners[type] = fn; }, removeEventListener() {}, contains: () => true, setAttribute() {}, removeAttribute() {},
  };
  V.enhance(report, V.createContext(spec, spec.cases || {}));
  if (!listeners.click) fail("enhance() attached no click handler for the run drawer");
  return i => {
    body.innerHTML = "";
    const mark = { dataset: { run: String(i) } };
    listeners.click({ target: { closest: selector => selector === "[data-run]" ? mark : null } });
    return body.innerHTML;
  };
}

/** A document stub carrying embedded JSON blocks and one mount target; loading
 * the bundle with it runs autoMount() exactly as a browser would at load. */
function autoMountDocument(blocks) {
  const attributes = new Map();
  const target = {
    innerHTML: "", ownerDocument: null,
    hasAttribute: name => attributes.has(name), getAttribute: name => attributes.has(name) ? attributes.get(name) : null,
    setAttribute: (name, value) => { attributes.set(name, String(value)); }, removeAttribute: name => { attributes.delete(name); },
    matches: () => false, querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, contains: () => false,
  };
  const win = { Event: class { constructor(type) { this.type = type; } }, addEventListener() {}, removeEventListener() {}, scrollY: 0 };
  const nodes = Object.fromEntries(Object.entries(blocks).map(([id, text]) => [id, { getAttribute: name => name === "type" ? "application/json" : null, textContent: text }]));
  const document = {
    readyState: "complete", defaultView: win, dispatchEvent() { return true; }, addEventListener() {},
    getElementById: id => nodes[id] || null, querySelector: selector => selector === "[data-av-mount]" ? target : null,
  };
  target.ownerDocument = document;
  return { document, target, attributes };
}

module.exports = {
  VISUALS, loadVisuals, plain, test, report,
  fail, includes, excludes, equal, ok, count, throws, element, sectionIds, snippet,
  drawerOpener, autoMountDocument,
};
