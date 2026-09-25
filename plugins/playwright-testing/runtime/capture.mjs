import { randomUUID } from 'node:crypto';
import { observeContext } from './discovery.mjs';
import { conciseError, waitForReadiness, withinDeadline } from './readiness.mjs';

const locatorFor = (page, value) => typeof value === 'string' ? page.locator(value) : value;

function serializableClue(value) {
  if (value === undefined) return undefined;
  try {
    return JSON.parse(JSON.stringify(value, (_key, item) => {
      if (['function', 'symbol', 'bigint'].includes(typeof item)) throw new Error('Non-JSON value');
      return item;
    }));
  } catch { throw new TypeError('captureScope must be JSON-serializable; supply a selector or reproduction description instead of browser handles.'); }
}

function describeLocator(value) {
  if (!value) return undefined;
  if (typeof value === 'string') return { kind: 'selector', selector: value };
  const description = typeof value.description === 'function' ? value.description() : undefined;
  // describe() creates another Locator; clearing its presentation label exposes
  // its diagnostic expression without reading private selector fields.
  const locator = String(description && typeof value.describe === 'function' ? value.describe('') : value);
  return { kind: 'locator', ...(locator !== '[object Object]' ? { locator } : { opaque: true }), ...(typeof description === 'string' && description ? { description } : {}) };
}

async function observeSelection(locator, timeout, signal) {
  const handle = await locator.elementHandle({ timeout });
  if (!handle) throw new Error('The selected element is unavailable.');
  try {
    const frame = await withinDeadline(() => handle.ownerFrame(), timeout, signal);
    const ancestry = [];
    for (let current = frame; current; current = current.parentFrame()) ancestry.unshift({ url: current.url(), name: current.name(), index: current.parentFrame()?.childFrames().indexOf(current) ?? 0 });
    const observation = await withinDeadline(() => handle.evaluate(element => {
      const bounds = element.getBoundingClientRect();
      const name = String(element.getAttribute('aria-label') || Array.from(element.labels || []).map(label => label.textContent || '').join(' ').trim() || element.textContent || '').replace(/\s+/g, ' ').trim();
      return {
        identity: { tag: element.localName, domId: element.id || null, testId: element.getAttribute('data-testid'), role: element.getAttribute('role'), name: name.slice(0, 2000), nameLength: name.length },
        frame: { url: location.href, name: window.name, viewport: { width: innerWidth, height: innerHeight }, scroll: { x: scrollX, y: scrollY } },
        boundsInFrame: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height },
        scroll: { x: element.scrollLeft, y: element.scrollTop, width: element.scrollWidth, height: element.scrollHeight, clientWidth: element.clientWidth, clientHeight: element.clientHeight },
      };
    }), timeout, signal);
    const boundsInPage = await withinDeadline(() => handle.boundingBox(), timeout, signal);
    return { ...observation, frame: { ...observation.frame, ancestry }, boundsInPage };
  } finally { await withinDeadline(() => handle.dispose(), 2000).catch(() => {}); }
}

function pageState() {
  return {
    url: location.href, title: document.title,
    viewport: { width: innerWidth, height: innerHeight },
    scroll: { x: scrollX, y: scrollY },
    document: { width: document.documentElement?.scrollWidth, height: document.documentElement?.scrollHeight },
    deviceScaleFactor: devicePixelRatio,
    observedPreferences: { colorScheme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light', reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches },
  };
}

async function rememberScroll(page, deadline, signal) {
  const frames = page.frames().slice(0, 50), snapshots = [], warnings = [];
  if (page.frames().length > frames.length) warnings.push({ stage: 'scroll-preservation', message: 'Scroll snapshot reached its 50-frame observation limit.' });
  for (const frame of frames) {
    try {
      const handle = await withinDeadline(() => frame.evaluateHandle(() => {
        const elements = [], stack = [document.documentElement];
        let visited = 0;
        while (stack.length && visited++ < 20000) {
          const element = stack.pop();
          if (!element) continue;
          if (element.scrollLeft || element.scrollTop || element.scrollWidth > element.clientWidth || element.scrollHeight > element.clientHeight) elements.push({ element, x: element.scrollLeft, y: element.scrollTop });
          for (const child of element.children) stack.push(child);
          if (element.shadowRoot) for (const child of element.shadowRoot.children) stack.push(child);
        }
        return { url: location.href, x: scrollX, y: scrollY, elements, truncated: stack.length > 0 };
      }), Math.min(2000, deadline - Date.now()), signal);
      snapshots.push({ frame, handle });
      const truncated = await withinDeadline(() => handle.evaluate(value => value.truncated), Math.min(2000, deadline - Date.now()), signal);
      if (truncated) warnings.push({ stage: 'scroll-preservation', message: 'Scroll snapshot reached its 20,000-element observation limit.' });
    } catch (error) { warnings.push({ stage: 'scroll-preservation', url: frame.url(), message: conciseError(error) }); }
  }
  return { snapshots, warnings };
}

async function restoreScroll(snapshots) {
  const issues = [];
  await Promise.all(snapshots.map(async ({ handle, frame }) => {
    try {
      await withinDeadline(() => handle.evaluate(snapshot => {
        if (location.href !== snapshot.url) return { restored: false, reason: 'The frame navigated during capture.' };
        const missing = [];
        for (const { element, x, y } of snapshot.elements) {
          if (element.isConnected) element.scrollTo({ left: x, top: y, behavior: 'instant' });
          else missing.push({ identity: { tag: element.localName, domId: element.id || null, testId: element.getAttribute('data-testid') }, expected: { x, y } });
        }
        scrollTo({ left: snapshot.x, top: snapshot.y, behavior: 'instant' });
        return { restored: missing.length === 0, missing: missing.slice(0, 20), missingCount: missing.length };
      }).then(result => {
        if (result.reason) issues.push({ stage: 'scroll-restoration', url: frame.url(), message: result.reason });
        for (const missing of result.missing || []) issues.push({ stage: 'scroll-restoration', url: frame.url(), ...missing, message: 'A scrollable element was replaced; its original scroll position needs restoration.' });
        if (result.missingCount > 20) issues.push({ stage: 'scroll-restoration', url: frame.url(), missingCount: result.missingCount - 20, message: 'Additional scrollable elements were replaced.' });
      }), 2000);
    } catch (error) { issues.push({ stage: 'scroll-restoration', url: frame.url(), message: conciseError(error) }); }
    finally { await withinDeadline(() => handle.dispose(), 2000).catch(() => {}); }
  }));
  return issues;
}

function sameNativeIdentity(left, right) {
  return left.tag === right.tag && Boolean(left.domId && left.domId === right.domId || left.testId && left.testId === right.testId);
}

async function restoreContainer(container, initial) {
  const expected = { x: initial.scroll.x, y: initial.scroll.y };
  try {
    const current = await observeSelection(container, 2000);
    const frameMatches = JSON.stringify(current.frame.ancestry) === JSON.stringify(initial.frame.ancestry);
    if (!frameMatches) return { status: 'partial', expected, observed: current.scroll, reason: 'The scroll container now belongs to a different frame.' };
    const atExpectedPosition = Math.abs(current.scroll.x - expected.x) < 1 && Math.abs(current.scroll.y - expected.y) < 1;
    if (atExpectedPosition) return { status: 'restored', expected, observed: current.scroll, recovered: false };
    if (!sameNativeIdentity(initial.identity, current.identity)) return { status: 'partial', expected, observed: current.scroll, reason: 'The live scroll target has no matching native identity for safe restoration.' };
    await container.evaluate((element, point) => element.scrollTo({ left: point.x, top: point.y, behavior: 'instant' }), expected, { timeout: 2000 });
    // Observe after the scroll event's render turn, including a possible remount.
    await withinDeadline(() => container.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))), 2000);
    const after = await observeSelection(container, 2000);
    const restored = sameNativeIdentity(initial.identity, after.identity) && JSON.stringify(after.frame.ancestry) === JSON.stringify(initial.frame.ancestry) && Math.abs(after.scroll.x - expected.x) < 1 && Math.abs(after.scroll.y - expected.y) < 1;
    return { status: restored ? 'restored' : 'partial', expected, observed: after.scroll, recovered: restored, ...(!restored ? { reason: 'The live scroll target did not retain the restored position.' } : {}) };
  } catch (error) { return { status: 'partial', expected, reason: conciseError(error) }; }
}

async function scrollMetrics(page, container, timeout) {
  const measure = element => {
    const windowScroll = !element;
    const el = element || document.scrollingElement || document.documentElement;
    const width = windowScroll ? innerWidth : el.clientWidth, height = windowScroll ? innerHeight : el.clientHeight;
    return { x: windowScroll ? scrollX : el.scrollLeft, y: windowScroll ? scrollY : el.scrollTop, width, height, scrollWidth: el.scrollWidth, scrollHeight: el.scrollHeight, maxX: Math.max(0, el.scrollWidth - width), maxY: Math.max(0, el.scrollHeight - height) };
  };
  return container ? container.evaluate(measure, undefined, { timeout }) : withinDeadline(() => page.evaluate(measure, null), timeout);
}

async function moveScroll(page, container, position, timeout) {
  const move = (element, next) => (element || window).scrollTo({ left: next.x, top: next.y, behavior: 'instant' });
  if (container) await container.evaluate(move, position, { timeout });
  else await withinDeadline(() => page.evaluate(position => scrollTo({ left: position.x, top: position.y, behavior: 'instant' }), position), timeout);
}

/** Capture current evidence. Completion describes collection, not an application's correctness. */
export async function capture(page, options = {}) {
  const { run, label = 'Observed state', id = randomUUID(), state = {}, taskId, readiness, target, region, scroll, captureScope: suppliedScope, diagnostics = true, signal, timeout = 30000, screenshotOptions = {}, ...context } = options;
  if (!run?.record || !run?.storeBlob) throw new TypeError('capture requires an evidence run with record() and storeBlob().');
  if (!Number.isFinite(timeout) || timeout <= 0) throw new TypeError('capture.timeout must be a positive number.');
  if (target && region) throw new TypeError('Choose a target or a region for a capture.');
  if (region && (['x', 'y', 'width', 'height'].some(key => !Number.isFinite(region[key])) || region.x < 0 || region.y < 0 || region.width <= 0 || region.height <= 0)) throw new TypeError('region requires non-negative x/y and positive width/height.');
  if (screenshotOptions.path) throw new TypeError('Evidence run owns screenshot storage; omit screenshotOptions.path.');
  if (screenshotOptions.clip) throw new TypeError('Use region to retain screenshot clipping in the capture evidence.');
  const scrolling = scroll ? (scroll === true ? {} : scroll) : undefined;
  const axis = scrolling?.axis ?? 'y', maxFrames = scrolling?.maxFrames ?? 40, overlap = scrolling?.overlap ?? 0.18;
  if (scrolling && !['x', 'y', 'both'].includes(axis)) throw new TypeError('scroll.axis must be x, y or both.');
  if (!Number.isInteger(maxFrames) || maxFrames < 1 || !Number.isFinite(overlap) || overlap < 0 || overlap >= 1) throw new TypeError('scroll.maxFrames must be a positive integer and overlap must be from 0 to less than 1.');
  if (scrolling && (region || screenshotOptions.fullPage)) throw new TypeError('Scroll sequences use viewport or container captures; omit region and fullPage.');
  const container = locatorFor(page, scrolling?.container);
  const subject = locatorFor(page, target) || container;
  for (const locator of [container, subject]) if (locator?.page && locator.page() !== page) throw new TypeError('The capture target must belong to the supplied page.');
  const scopeClue = serializableClue(suppliedScope);
  const recordedScreenshotOptions = {};
  for (const key of ['type', 'quality', 'fullPage', 'scale', 'animations', 'caret', 'omitBackground', 'style', 'maskColor']) if (screenshotOptions[key] !== undefined) recordedScreenshotOptions[key] = serializableClue(screenshotOptions[key]);
  if (screenshotOptions.mask) recordedScreenshotOptions.mask = screenshotOptions.mask.map(describeLocator);
  const captureScope = {
    mode: scrolling ? 'scroll-sequence' : subject ? 'element' : region ? 'region' : screenshotOptions.fullPage ? 'full-page' : 'viewport',
    ...(target ? { target: describeLocator(target) } : {}),
    ...(region ? { region: serializableClue(region) } : {}),
    ...(scrolling ? { scroll: { container: scrolling.container ? describeLocator(scrolling.container) : { kind: 'document' }, axis, overlap, maxFrames } } : {}),
    ...(Object.keys(recordedScreenshotOptions).length ? { screenshotOptions: recordedScreenshotOptions } : {}),
    ...(scopeClue !== undefined ? { reproduction: scopeClue } : {}),
  };
  if ((captureScope.target?.opaque || captureScope.scroll?.container?.opaque || recordedScreenshotOptions.mask?.some(item => item.opaque)) && scopeClue === undefined) throw new TypeError('An opaque Locator requires a JSON-safe captureScope reproduction clue.');
  const started = Date.now(), deadline = started + timeout;
  const remaining = () => Math.max(1, deadline - Date.now());
  const warnings = [], images = [], observations = [];
  let ownObserver, observer = diagnostics, saved = { snapshots: [], warnings: [] }, initialState = { url: page.url() }, status = 'complete', initialContainer, restoration;
  if (diagnostics === true) observer = ownObserver = observeContext(page.context());
  const coverage = { mode: captureScope.mode, endReached: !scrolling, maxFrames: scrolling ? maxFrames : 1 };
  const snapshotDiagnostics = async () => {
    if (!observer) return undefined;
    try { return typeof observer === 'function' ? await withinDeadline(() => observer(), 2000) : typeof observer.snapshot === 'function' ? await withinDeadline(() => observer.snapshot(), 2000) : observer; }
    catch (error) { return { error: conciseError(error) }; }
  };
  const check = async () => {
    const setting = typeof readiness === 'function' ? { check: readiness } : readiness === false ? { fonts: false, images: false, layout: false } : readiness || {};
    const result = await waitForReadiness(page, { ...setting, timeout: Math.min(setting.timeout ?? 5000, remaining()), signal });
    observations.push(result);
    if (result.status !== 'ready') status = result.status === 'cancelled' ? 'cancelled' : 'partial';
    return result;
  };
  try {
    initialState = await withinDeadline(() => page.evaluate(pageState), remaining(), signal);
    saved = await rememberScroll(page, deadline, signal);
    warnings.push(...saved.warnings);
    if (container) initialContainer = await observeSelection(container, remaining(), signal);
    if (subject) await subject.scrollIntoViewIfNeeded({ timeout: remaining() });
    let metrics;
    if (scrolling) {
      metrics = await scrollMetrics(page, container, remaining());
      if (metrics.width < 1 || metrics.height < 1) throw new Error('The scroll target has no visible capture area.');
      const initial = { x: axis === 'y' ? metrics.x : 0, y: axis === 'x' ? metrics.y : 0 };
      await moveScroll(page, container, initial, remaining());
      coverage.axis = axis;
      coverage.initial = metrics;
    }
    let prior;
    for (let index = 0; index < (scrolling ? maxFrames : 1); index++) {
      if (signal?.aborted) { status = 'cancelled'; break; }
      if (Date.now() >= deadline) { status = 'partial'; warnings.push({ stage: 'capture', message: 'Capture deadline reached; completed images are retained.' }); break; }
      const currentReadiness = await check();
      if (signal?.aborted) { status = 'cancelled'; break; }
      const observed = await withinDeadline(() => page.evaluate(pageState), remaining(), signal);
      if (scrolling) metrics = await scrollMetrics(page, container, remaining());
      if (scrolling && prior && metrics.x === prior.x && metrics.y === prior.y) {
        status = 'partial';
        warnings.push({ stage: 'scroll', message: 'The target stopped moving before the observed end.' });
        break;
      }
      const opts = { ...screenshotOptions, type: screenshotOptions.type ?? 'png', ...(region ? { clip: region } : {}), timeout: remaining() };
      if (subject && opts.fullPage) throw new TypeError('Element capture does not accept fullPage.');
      const selection = subject ? { subject: await observeSelection(subject, remaining(), signal) } : undefined;
      if (selection && container) selection.scrollContainer = container === subject ? selection.subject : await observeSelection(container, remaining(), signal);
      const bytes = subject ? await subject.screenshot(opts) : await page.screenshot(opts);
      const ref = await run.storeBlob(bytes, { extension: opts.type === 'jpeg' ? 'jpg' : 'png', mime: opts.type === 'jpeg' ? 'image/jpeg' : 'image/png' });
      const image = { ...ref, index, position: metrics || observed.scroll, observed, ...(selection ? { selection } : {}), ...(region ? { region } : {}), readiness: currentReadiness.status };
      images.push(image);
      await run.record({ type: 'capture-progress', captureId: id, label, state: { ...state, ...observed }, taskId, captureScope, images: [image], readiness: currentReadiness, status: 'partial', context });
      if (!scrolling) break;
      // Re-measure after capture because scroll-triggered rendering can change the extent.
      metrics = await scrollMetrics(page, container, remaining());
      coverage.last = metrics;
      const atRight = metrics.x >= metrics.maxX - 1, atBottom = metrics.y >= metrics.maxY - 1;
      coverage.endReached = axis === 'y' ? atBottom : axis === 'x' ? atRight : atRight && atBottom;
      if (coverage.endReached) break;
      if (index + 1 >= maxFrames) break;
      prior = { x: metrics.x, y: metrics.y };
      let next = { x: metrics.x, y: metrics.y };
      if (axis !== 'y' && !atRight) next.x = Math.min(metrics.maxX, metrics.x + Math.max(1, Math.floor(metrics.width * (1 - overlap))));
      else if (axis !== 'x') { next.y = Math.min(metrics.maxY, metrics.y + Math.max(1, Math.floor(metrics.height * (1 - overlap)))); if (axis === 'both') next.x = 0; }
      await moveScroll(page, container, next, remaining());
    }
    if (!coverage.endReached) { status = status === 'cancelled' ? status : 'partial'; coverage.limitReached = images.length >= maxFrames; }
  } catch (error) {
    status = signal?.aborted ? 'cancelled' : 'partial';
    warnings.push({ stage: 'capture', message: conciseError(error) });
  } finally {
    let restorationIssues = await restoreScroll(saved.snapshots);
    if (container && initialContainer) {
      const result = await restoreContainer(container, initialContainer);
      restoration = { container: result };
      if (result.status === 'restored' && result.recovered) {
        let reconciled = false;
        restorationIssues = restorationIssues.filter(issue => {
          if (!reconciled && issue.url === initialContainer.frame.url && issue.identity && sameNativeIdentity(issue.identity, initialContainer.identity) && issue.expected?.x === initialContainer.scroll.x && issue.expected?.y === initialContainer.scroll.y) { reconciled = true; return false; }
          return true;
        });
      }
      if (result.status !== 'restored') restorationIssues.push({ stage: 'scroll-restoration', captureScope: captureScope.scroll, expected: result.expected, observed: result.observed, message: result.reason });
    }
    warnings.push(...restorationIssues);
  }
  const observedDiagnostics = await snapshotDiagnostics();
  ownObserver?.close();
  if (warnings.length && status === 'complete') status = 'partial';
  const record = {
    ...context, type: 'capture', id, label, state: { ...state, ...initialState }, taskId, captureScope,
    ...(images[0]?.selection ? { selection: images[0].selection } : {}),
    ...(restoration ? { restoration } : {}),
    images, status, readiness: observations.length === 1 ? observations[0] : { status: observations.every(value => value.status === 'ready') && observations.length ? 'ready' : 'unsettled', observations },
    diagnostics: observedDiagnostics, warnings, coverage, elapsedMs: Date.now() - started,
  };
  return run.record(record);
}
