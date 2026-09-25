import { conciseError, withinDeadline } from './readiness.mjs';

function inspectDocument({ maxItems, maxNodes, maxTextLength, includeHidden }) {
  const links = [], controls = [], scrollContainers = [], regions = [], counts = { links: 0, controls: 0, scrollContainers: 0, regions: 0 };
  const stack = [document.documentElement];
  const occurrences = new Map();
  let visited = 0, shadowRoots = 0;
  const text = el => String(el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => el.getRootNode().getElementById?.(id)?.textContent || '').join(' ').trim() || Array.from(el.labels || []).map(label => label.textContent || '').join(' ').trim() || el.getAttribute('alt') || el.textContent || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
  const cssPart = el => {
    const testId = el.getAttribute('data-testid');
    let part = el.id ? `#${CSS.escape(el.id)}` : testId ? `[data-testid="${CSS.escape(testId)}"]` : el.localName;
    const parent = el.parentElement || el.getRootNode();
    if (parent?.children) {
      const siblings = Array.from(parent.children).filter(item => item.localName === el.localName);
      if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(el) + 1})`;
    }
    return part;
  };
  const selector = el => {
    const parts = [];
    for (let cursor = el; cursor; cursor = cursor.parentElement || cursor.getRootNode().host) parts.unshift(cssPart(cursor));
    // Playwright CSS locators pierce open shadow roots. These clues belong to this observation.
    return parts.join(' ');
  };
  const add = (kind, array, el, details) => {
    counts[kind]++;
    if (array.length >= maxItems) return;
    const name = text(el), css = selector(el);
    const key = JSON.stringify([kind, el.localName, el.id, name, el.getAttribute('href')]);
    const occurrence = occurrences.get(key) || 0;
    occurrences.set(key, occurrence + 1);
    const b = el.getBoundingClientRect(), style = getComputedStyle(el);
    array.push({
      id: `${kind}-${counts[kind]}`, tag: el.localName, name: name.slice(0, maxTextLength), nameLength: name.length, nameTruncated: name.length > maxTextLength, occurrence,
      domId: el.id || undefined, testId: el.getAttribute('data-testid') || undefined,
      visible: b.width > 0 && b.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
      inViewport: b.bottom > 0 && b.right > 0 && b.top < innerHeight && b.left < innerWidth,
      bounds: { x: b.x, y: b.y, width: b.width, height: b.height },
      locator: { css, scope: 'observation', note: 'Re-observe after navigation or relevant DOM changes.' },
      ...details,
    });
  };
  while (stack.length && visited < maxNodes) {
    const el = stack.pop();
    if (!el) continue;
    visited++;
    for (let i = el.children.length - 1; i >= 0; i--) stack.push(el.children[i]);
    if (el.shadowRoot) {
      shadowRoots++;
      for (let i = el.shadowRoot.children.length - 1; i >= 0; i--) stack.push(el.shadowRoot.children[i]);
    }
    const style = getComputedStyle(el), box = el.getBoundingClientRect();
    const visible = box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    if (!visible && !includeHidden) continue;
    const role = el.getAttribute('role');
    if (el.matches('a[href],area[href]') || role === 'link') {
      const href = el.getAttribute('href');
      let resolved;
      try { if (href !== null) resolved = new URL(href, document.baseURI).href; } catch { /* Preserve malformed author input below. */ }
      add('links', links, el, { href, url: resolved, target: el.getAttribute('target') || undefined, download: el.hasAttribute('download'), role: role || 'link' });
    }
    const controlRoles = ['button', 'checkbox', 'combobox', 'listbox', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'option', 'radio', 'scrollbar', 'searchbox', 'slider', 'spinbutton', 'switch', 'tab', 'textbox', 'treeitem'];
    if (el.matches('button,input:not([type="hidden"]),select,textarea,summary,[contenteditable="true"]') || controlRoles.includes(role)) {
      const inputType = el.getAttribute('type') || undefined;
      const implicitRole = el.localName === 'button' || el.localName === 'summary' ? 'button' : el.localName === 'select' ? (el.multiple ? 'listbox' : 'combobox') : el.localName === 'textarea' ? 'textbox' : el.localName === 'input' ? ({ checkbox: 'checkbox', radio: 'radio', range: 'slider', number: 'spinbutton', button: 'button', submit: 'button', reset: 'button', search: 'searchbox' }[inputType] || 'textbox') : undefined;
      add('controls', controls, el, {
        role: role || implicitRole, inputType, disabled: Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true',
        expanded: el.getAttribute('aria-expanded'), selected: el.getAttribute('aria-selected'), checked: el.getAttribute('aria-checked') ?? (typeof el.checked === 'boolean' ? el.checked : undefined),
        placeholder: el.getAttribute('placeholder') || undefined,
      });
    }
    if (el !== document.documentElement && el !== document.body && ((/(auto|scroll|overlay)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 1) || (/(auto|scroll|overlay)/.test(style.overflowX) && el.scrollWidth > el.clientWidth + 1))) {
      add('scrollContainers', scrollContainers, el, { scroll: { x: el.scrollLeft, y: el.scrollTop, width: el.scrollWidth, height: el.scrollHeight, clientWidth: el.clientWidth, clientHeight: el.clientHeight }, virtualized: 'unknown' });
    }
    if (el.matches('dialog,nav,main,aside') || ['dialog', 'alertdialog', 'navigation', 'main', 'tablist'].includes(role)) add('regions', regions, el, { role: role || ({ nav: 'navigation', dialog: 'dialog', main: 'main', aside: 'complementary' }[el.localName]), open: el.localName === 'dialog' ? el.open : undefined });
  }
  return {
    title: document.title, url: location.href, baseURI: document.baseURI,
    viewport: { width: innerWidth, height: innerHeight },
    document: { width: document.documentElement?.scrollWidth, height: document.documentElement?.scrollHeight, x: scrollX, y: scrollY },
    links, controls, scrollContainers, regions, counts, visited, openShadowRoots: shadowRoots,
    truncated: stack.length > 0 || Object.values(counts).some(n => n > maxItems),
  };
}

/** Observe candidate destinations and controls without navigating or interacting. */
export async function discover(page, options = {}) {
  const maxItems = options.maxItems ?? 500, maxNodes = options.maxNodes ?? 20000, maxFrames = options.maxFrames ?? 50, maxTextLength = options.maxTextLength ?? 2000, timeout = options.timeout ?? 10000;
  for (const [name, value] of Object.entries({ maxItems, maxNodes, maxFrames, maxTextLength, timeout })) if (!Number.isInteger(value) || value < 1) throw new TypeError(`${name} must be a positive integer.`);
  const began = Date.now(), all = page.frames(), selected = all.slice(0, maxFrames);
  const ids = new Map(all.map((frame, index) => [frame, `frame-${index}`]));
  const frames = await Promise.all(selected.map(async frame => {
    const identity = { id: ids.get(frame), parentId: ids.get(frame.parentFrame()) ?? null, name: frame.name(), url: frame.url() };
    try {
      const facts = await withinDeadline(() => frame.evaluate(inspectDocument, { maxItems, maxNodes, maxTextLength, includeHidden: Boolean(options.includeHidden) }), timeout - (Date.now() - began), options.signal);
      for (const kind of ['links', 'controls', 'scrollContainers', 'regions']) for (const fact of facts[kind]) { fact.id = `${identity.id}:${fact.id}`; fact.locator.frameId = identity.id; }
      return { ...identity, ...facts, status: 'observed' };
    } catch (error) { return { ...identity, status: 'unavailable', error: conciseError(error) }; }
  }));
  return { url: page.url(), observedAt: new Date().toISOString(), frames, truncated: all.length > selected.length || frames.some(frame => frame.truncated), limits: { maxItems, maxNodes, maxFrames, maxTextLength }, scope: 'Current rendered DOM and open shadow roots; controls and routes may appear after further interaction.' };
}

/** Bounded diagnostics attached to every existing and subsequently opened page. */
export function observeContext(context, { limit = 200, messageLimit = 4000 } = {}) {
  if (!Number.isInteger(limit) || limit < 1 || !Number.isInteger(messageLimit) || messageLimit < 1) throw new TypeError('Diagnostic limits must be positive integers.');
  const events = [], pages = new Map();
  let dropped = 0, sequence = 0, pageNumber = 0, closed = false, nextIndex = 0;
  const append = event => {
    if (closed) return;
    const value = { sequence: ++sequence, at: new Date().toISOString(), ...event };
    if (events.length < limit) events.push(value);
    else { events[nextIndex] = value; nextIndex = (nextIndex + 1) % limit; dropped++; }
  };
  const attach = page => {
    if (closed || pages.has(page)) return;
    const pageId = `page-${++pageNumber}`;
    const base = () => ({ pageId, url: page.url() });
    const handlers = {
      console: message => { if (['warning', 'error'].includes(message.type())) append({ ...base(), kind: 'console', level: message.type(), message: message.text().slice(0, messageLimit), location: message.location() }); },
      pageerror: error => append({ ...base(), kind: 'pageerror', message: String(error.message).slice(0, messageLimit) }),
      requestfailed: request => append({ ...base(), kind: 'requestfailed', request: { url: request.url(), method: request.method(), resourceType: request.resourceType() }, message: request.failure()?.errorText }),
      response: response => { if (response.status() >= 400) append({ ...base(), kind: 'http-response', request: { url: response.url(), method: response.request().method(), resourceType: response.request().resourceType() }, status: response.status() }); },
      crash: () => append({ ...base(), kind: 'crash' }),
      close: () => { append({ ...base(), kind: 'page-closed' }); detach(page); },
    };
    pages.set(page, handlers);
    for (const [event, handler] of Object.entries(handlers)) page.on(event, handler);
    append({ ...base(), kind: 'page-observed' });
  };
  const detach = page => {
    const handlers = pages.get(page);
    if (!handlers) return;
    for (const [event, handler] of Object.entries(handlers)) page.off(event, handler);
    pages.delete(page);
  };
  for (const page of context.pages()) attach(page);
  context.on('page', attach);
  const close = () => { if (closed) return; closed = true; context.off('page', attach); context.off('close', close); for (const page of [...pages.keys()]) detach(page); };
  context.on('close', close);
  return { snapshot: () => ({ events: structuredClone(dropped ? [...events.slice(nextIndex), ...events.slice(0, nextIndex)] : events), dropped, observedPages: pageNumber, attachedPages: pages.size, limit, closed }), close };
}
