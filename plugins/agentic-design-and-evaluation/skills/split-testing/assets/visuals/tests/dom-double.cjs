// Bounded DOM/event doubles for source behavior checks, not browser layout or accessibility proof.
const assert = require("node:assert/strict");

class EventSurface {
  listeners = new Map();
  addEventListener(type, callback, capture = false) {
    const list = this.listeners.get(type) || [];
    list.push({ callback, capture });
    this.listeners.set(type, list);
  }
  removeEventListener(type, callback, capture = false) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter(item => item.callback !== callback || item.capture !== capture));
  }
  dispatchEvent(event) {
    event.target ||= this;
    event.preventDefault ||= function () { this.defaultPrevented = true; };
    event.stopPropagation ||= function () { this.propagationStopped = true; };
    const ancestors = [];
    for (let parent = this.parentNode; parent; parent = parent.parentNode) ancestors.push(parent);
    const call = (surface, capture) => {
      for (const item of [...(surface.listeners.get(event.type) || [])]) if (item.capture === capture) item.callback(event);
    };
    for (const parent of [...ancestors].reverse()) { call(parent, true); if (event.propagationStopped) return !event.defaultPrevented; }
    call(this, true);
    call(this, false);
    if (event.bubbles !== false && !event.propagationStopped) for (const parent of ancestors) { call(parent, false); if (event.propagationStopped) break; }
    return !event.defaultPrevented;
  }
  get listenerCount() { return [...this.listeners.values()].reduce((sum, list) => sum + list.length, 0); }
}

class NodeDouble extends EventSurface {
  constructor(type, document) { super(); this.nodeType = type; this.ownerDocument = document; this.childNodes = []; this.parentNode = null; }
  cloneNode(deep = false) {
    const copy = this.nodeType === 3 || this.nodeType === 8 ? new TextDouble(this.textContent, this.ownerDocument, this.nodeType) : this.ownerDocument.createElement(this.tagName.toLowerCase());
    if (this.attributes) for (const [name, value] of this.attributes.entries()) copy.setAttribute(name, value);
    if(this.namespaceURI)copy.namespaceURI=this.namespaceURI;
    if (deep) for (const child of this.childNodes) copy.appendChild(child.cloneNode(true));
    return copy;
  }
  replaceChildren(...nodes) { for (const child of [...this.childNodes]) child.remove(); for (const node of nodes) this.appendChild(node); }
  replaceWith(node) { if (this.parentNode) this.parentNode.replaceChild(node, this); }
  append(...nodes) { for (const node of nodes) this.appendChild(typeof node === 'string' ? this.ownerDocument.createTextNode(node) : node); }
  get firstElementChild() { return this.children[0] || null; }
  get nextElementSibling() { let node = this.nextSibling; while (node && node.nodeType !== 1) node = node.nextSibling; return node || null; }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length-1] || null; }
  get children() { return this.childNodes.filter(node=>node.nodeType===1); }
  get parentElement() { return this.parentNode?.nodeType === 1 ? this.parentNode : null; }
  get nextSibling() { const siblings = this.parentNode?.childNodes || []; return siblings[siblings.indexOf(this) + 1] || null; }
  appendChild(child) { assert.equal(child.contains(this), false, "Cannot move an ancestor into its own descendant"); child.remove(); this.childNodes.push(child); child.parentNode = this; return child; }
  insertBefore(child, reference) {
    if (reference === null) return this.appendChild(child);
    assert.equal(child.contains(this), false, "Cannot move an ancestor into its own descendant"); child.remove(); const index = this.childNodes.indexOf(reference); assert.ok(index >= 0);
    this.childNodes.splice(index, 0, child); child.parentNode = this; return child;
  }
  replaceChild(child, previous) { this.insertBefore(child, previous); previous.remove(); return previous; }
  remove() { if (this.parentNode) { const siblings = this.parentNode.childNodes; siblings.splice(siblings.indexOf(this), 1); this.parentNode = null; } }
  contains(node) { return this === node || this.childNodes.some(child => child.contains(node)); }
  get textContent() { return this.childNodes.filter(child => child.nodeType !== 8).map(child => child.textContent).join(""); }
  set textContent(text) { for (const child of [...this.childNodes]) child.remove(); if (text !== "" && text !== null) this.appendChild(new TextDouble(String(text), this.ownerDocument)); }
  get isConnected() { return this.ownerDocument?.body.contains(this) || false; }
}
class TextDouble extends NodeDouble {
  constructor(value, document, type = 3) { super(type, document); this.value = value; }
  get textContent() { return this.value; }
  set textContent(value) { this.value = value; }
}

function matchesSelector(element, selector) {
  return selector.split(",").some(compound => {
    compound = compound.trim();
    const tag = compound.match(/^[a-z][a-z0-9-]*/i)?.[0];
    if (tag && element.tagName.toLowerCase() !== tag.toLowerCase()) return false;
    for (const [, name] of compound.matchAll(/\.([a-zA-Z0-9_-]+)/g)) if (!element.classList.contains(name)) return false;
    for (const [, name, , value] of compound.matchAll(/\[([^\]=]+)(?:=(["'])(.*?)\2)?\]/g)) {
      if (!element.hasAttribute(name)) return false;
      if (value !== undefined && element.getAttribute(name) !== value) return false;
    }
    return true;
  });
}
class AttributesDouble extends Map { *[Symbol.iterator](){for(const[name,value]of this.entries())yield {name,value};} get length(){return this.size;} }

class ElementDouble extends NodeDouble {
  constructor(tag, document) {
    super(1, document); this.tagName = tag.toUpperCase(); this.attributes = new AttributesDouble(); this.clientWidth = 600; this.clientHeight = 300; this.scrollWidth = 600; this.scrollHeight = 300; this.scrollLeft = 0; this.scrollTop = 0; this.checked = false;
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      toggle: (name, enabled) => {
        const tokens = new Set(this.className.split(/\s+/).filter(Boolean));
        const add = enabled === undefined ? !tokens.has(name) : enabled;
        if (add) tokens.add(name); else tokens.delete(name);
        this.className = [...tokens].join(" "); return add;
      },
      add: name => this.classList.toggle(name, true),
      remove: name => this.classList.toggle(name, false),
    };
    const readStyle = () => Object.fromEntries((this.getAttribute("style") || "").split(";").filter(Boolean).map(pair => ([pair.slice(0,pair.indexOf(":")),pair.slice(pair.indexOf(":")+1)])));
    const setStyle = (property, value) => { const styles = readStyle(); if (value === null) delete styles[property]; else styles[property] = value; this.setAttribute("style", Object.entries(styles).map(([key, item]) => `${key}:${item}`).join(";")); };
    this.style = new Proxy({}, {
      get: (_, property) => property === "cssText" ? this.getAttribute("style") || "" : property === "setProperty" ? (key, value) => setStyle(key, value)
        : property === "removeProperty" ? key => setStyle(key, null)
        : property === "getPropertyValue" ? key => readStyle()[key] || "" : property === "getPropertyPriority" ? () => "" : readStyle()[property] || "",
      set: (_, property, value) => { if(property === "cssText")this.setAttribute("style",value);else setStyle(property, value); return true; },
    });
  }
  get localName() { return this.tagName.toLowerCase(); }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  hasAttribute(name) { return this.attributes.has(name); }
  get id() { return this.getAttribute("id") || ""; }
  set id(value) { this.setAttribute("id", value); }
  get className() { return this.getAttribute("class") || ""; }
  set className(value) { this.setAttribute("class", value); }
  get hidden() { return this.hasAttribute("hidden"); }
  set hidden(value) { value ? this.setAttribute("hidden", "") : this.removeAttribute("hidden"); }
  get open() { return this.hasAttribute("open"); }
  set open(value) { value ? this.setAttribute("open", "") : this.removeAttribute("open"); }
  get disabled() { return this.hasAttribute("disabled"); }
  set disabled(value) { value ? this.setAttribute("disabled", "") : this.removeAttribute("disabled"); }
  get options() { return this.querySelectorAll("option"); }
  get value() { return this.currentValue ?? this.getAttribute("value") ?? (this.tagName === "SELECT" ? this.options[0]?.value : "") ?? ""; }
  set value(value) { this.currentValue = String(value); }
  set innerHTML(_) { throw new Error("The interaction layer must not inject HTML"); }
  matches(selector) { return matchesSelector(this, selector); }
  closest(selector) { for (let element = this; element; element = element.parentElement) if (element.matches(selector)) return element; return null; }
  querySelectorAll(selector) {
    const result = [];
    const visit = node => { for (const child of node.childNodes) { if (child.nodeType !== 1) continue; if (child.matches(selector)) result.push(child); visit(child); } };
    visit(this); return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  focus() { this.ownerDocument.activeElement = this; }
  scrollIntoView(options) { this.lastScroll = options; }
  getBoundingClientRect() { return { width: this.clientWidth }; }
  animate(frames, options) {
    const animation = { frames, options, cancelled: false, finished: new Promise(() => {}), cancel() { this.cancelled = true; } };
    this.ownerDocument.animations.push(animation); return animation;
  }
}
class DialogDouble extends ElementDouble {
  showModal() { assert.ok(this.isConnected); if (this.ownerDocument.rejectDialog) throw new Error("Modal unavailable"); this.open = true; }
  close() { if (!this.open) return; this.open = false; this.ownerDocument.pending.push(() => this.dispatchEvent({ type: "close", bubbles: false })); }
}
class WindowDouble extends EventSurface {
  constructor() { super(); this.location = { hash: "" }; this.media = new EventSurface(); this.media.matches = false; }
  matchMedia(query) { assert.equal(query, "(prefers-reduced-motion: reduce)"); return this.media; }
}
class DocumentDouble extends NodeDouble {
  constructor() {
    super(9, null); this.ownerDocument = this; this.defaultView = new WindowDouble(); this.body = new ElementDouble("body", this); this.body.parentNode = this;
    this.childNodes = [this.body]; this.animations = []; this.pending = []; this.activeElement = this.body;
  }
  createElement(tag) { return tag === "dialog" && !this.noDialog ? new DialogDouble(tag, this) : new ElementDouble(tag, this); }
  createElementNS(namespace, tag) { const node=this.createElement(tag); node.namespaceURI=namespace; return node; }
  createDocumentFragment() { return new NodeDouble(11,this); }
  createTextNode(text) { return new TextDouble(text, this); }
  createComment(text) { return new TextDouble(text, this, 8); }
  getElementById(id) { return this.body.id === id ? this.body : this.body.querySelectorAll("[id]").find(element => element.id === id) || null; }
  querySelectorAll(selector) { return [...(this.body.matches(selector) ? [this.body] : []), ...this.body.querySelectorAll(selector)]; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  flush() { for (const callback of this.pending.splice(0)) callback(); }
}

function element(document, tag, attributes = {}, text) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function append(parent, tag, attributes = {}, text) { return parent.appendChild(element(parent.ownerDocument, tag, attributes, text)); }
function send(target, type, fields = {}) { const event = { type, bubbles: true, button: 0, defaultPrevented: false, ...fields }; target.dispatchEvent(event); return event; }
function click(target, fields = {}) { if (!target.disabled) return send(target, "click", fields); }

module.exports = { EventSurface, NodeDouble, TextDouble, ElementDouble, DialogDouble, WindowDouble, DocumentDouble, element, append, send, click };
