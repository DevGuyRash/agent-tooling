import { setTimeout as delay } from 'node:timers/promises';

/** Run an observation within a deadline. A supplied callback receives cancellation. */
export async function withinDeadline(work, timeout, signal) {
  if (signal?.aborted) throw signal.reason ?? new Error('Operation cancelled.');
  if (!(Number.isFinite(timeout) && timeout > 0)) throw new Error('Operation deadline reached.');
  let timer, abort;
  const interrupted = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('Operation deadline reached.')), timeout);
    if (signal) {
      abort = () => reject(signal.reason ?? new Error('Operation cancelled.'));
      signal.addEventListener('abort', abort, { once: true });
    }
  });
  try { return await Promise.race([Promise.resolve().then(work), interrupted]); }
  finally {
    clearTimeout(timer);
    if (abort) signal.removeEventListener('abort', abort);
  }
}

export function conciseError(error) {
  return String(error?.message ?? error).split('\n').slice(0, 3).join('\n').slice(0, 1200);
}

function positive(value, fallback, name) {
  const result = value ?? fallback;
  if (!Number.isFinite(result) || result <= 0) throw new TypeError(`${name} must be a positive number.`);
  return result;
}

// Executed in each frame. Open shadow roots are observable; closed roots are not.
function sampleDocument({ maxElements, fonts, images, layout }) {
  const pending = [], failed = [], geometry = [];
  const stack = [document.documentElement];
  let visited = 0;
  while (stack.length && visited < maxElements) {
    const el = stack.pop();
    if (!el) continue;
    visited++;
    for (let i = el.children.length - 1; i >= 0; i--) stack.push(el.children[i]);
    if (el.shadowRoot) for (let i = el.shadowRoot.children.length - 1; i >= 0; i--) stack.push(el.shadowRoot.children[i]);
    const rect = el.getBoundingClientRect(), style = getComputedStyle(el);
    const visible = rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    if (!visible) continue;
    // Only images intersecting this frame's viewport can hold a viewport capture open.
    if (images && el.tagName === 'IMG' && rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth) {
      const description = { src: el.currentSrc || el.getAttribute('src') || '', alt: el.alt || '' };
      if (!el.complete) pending.push(description);
      else if (el.naturalWidth === 0 && (el.currentSrc || el.getAttribute('src'))) failed.push(description);
    }
    if (layout) geometry.push([el.tagName, ...[rect.x, rect.y, rect.width, rect.height].map(n => Math.round(n * 2) / 2)]);
  }
  const root = document.documentElement;
  return {
    url: location.href, documentState: document.readyState,
    fonts: fonts ? (document.fonts?.status ?? 'unavailable') : 'ignored',
    pendingImages: pending, failedImages: failed, visited, truncated: stack.length > 0,
    geometry: layout ? JSON.stringify([innerWidth, innerHeight, root?.scrollWidth, root?.scrollHeight, geometry]) : '',
  };
}

/** Bounded observations of assets and layout; callers define application readiness with check(). */
export async function waitForReadiness(page, input = {}) {
  const options = typeof input === 'function' ? { check: input } : input === false ? { fonts: false, images: false, layout: false } : input ?? {};
  const timeout = positive(options.timeout, 5000, 'readiness.timeout');
  const sampleInterval = positive(options.sampleInterval, 100, 'readiness.sampleInterval');
  const stableFor = options.stableFor ?? 250;
  if (!Number.isFinite(stableFor) || stableFor < 0) throw new TypeError('readiness.stableFor must be a non-negative number.');
  const maxElements = options.maxElements ?? 3000;
  const maxFrames = options.maxFrames ?? 30;
  if (!Number.isInteger(maxElements) || maxElements < 1 || !Number.isInteger(maxFrames) || maxFrames < 1) throw new TypeError('readiness.maxElements and maxFrames must be positive integers.');
  const started = Date.now(), deadline = started + timeout;
  const controller = new AbortController();
  const relay = () => controller.abort(options.signal.reason);
  if (options.signal?.aborted) relay();
  else options.signal?.addEventListener('abort', relay, { once: true });
  const result = { status: 'unsettled', elapsedMs: 0, checks: [], samples: 0, frames: [], limits: { maxElements, maxFrames } };
  let signature, stableSince = started, lastError;
  try {
    while (Date.now() < deadline) {
      if (controller.signal.aborted) { result.status = 'cancelled'; break; }
      const frames = page.frames().slice(0, maxFrames);
      result.frameLimitReached = page.frames().length > frames.length;
      const samples = await Promise.all(frames.map(async (frame, index) => {
        try {
          return { index, name: frame.name(), ...await withinDeadline(() => frame.evaluate(sampleDocument, {
            maxElements, fonts: options.fonts !== false, images: options.images !== false, layout: options.layout !== false,
          }), deadline - Date.now(), controller.signal) };
        } catch (error) { return { index, name: frame.name(), url: frame.url(), error: conciseError(error) }; }
      }));
      result.samples++;
      const next = JSON.stringify(samples.map(frame => [frame.url, frame.geometry, frame.error]));
      if (next !== signature) { signature = next; stableSince = Date.now(); }
      result.frames = samples.map(({ geometry, ...frame }) => frame);
      const assetsReady = samples.every(frame => !frame.error && frame.documentState !== 'loading' && frame.fonts !== 'loading' && frame.pendingImages.length === 0);
      const layoutReady = options.layout === false || Date.now() - stableSince >= stableFor;
      let applicationReady = true;
      if (options.check) {
        try {
          const value = await withinDeadline(() => options.check(page, { signal: controller.signal, remainingMs: Math.max(0, deadline - Date.now()), observation: result.frames }), deadline - Date.now(), controller.signal);
          applicationReady = value === true || (value && value.ready === true);
          result.application = value === undefined ? { ready: false, reason: 'Readiness callback did not return true or {ready:true}.' } : value;
        } catch (error) { applicationReady = false; lastError = conciseError(error); }
      }
      result.checks = [
        { name: 'assets', satisfied: assetsReady },
        { name: 'layout', satisfied: layoutReady, stableForMs: Math.max(0, Date.now() - stableSince) },
        ...(options.check ? [{ name: 'application', satisfied: Boolean(applicationReady) }] : []),
      ];
      if (assetsReady && layoutReady && applicationReady && !result.frameLimitReached && samples.every(frame => !frame.truncated)) { result.status = 'ready'; break; }
      if (Date.now() < deadline) await delay(Math.min(sampleInterval, deadline - Date.now()), undefined, { signal: controller.signal }).catch(() => {});
    }
  } catch (error) { lastError = conciseError(error); }
  finally {
    if (options.signal?.aborted) result.status = 'cancelled';
    controller.abort(new Error('Readiness observation ended.'));
    options.signal?.removeEventListener('abort', relay);
    result.elapsedMs = Date.now() - started;
  }
  if (lastError) result.error = lastError;
  return result;
}
