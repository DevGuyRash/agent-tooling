import { fork } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { acquireProvider } from './platforms/provider.mjs';
import { atomicJSON, createOwnedRun, delay, findExecutable, OWNER_ENV, processIdentity, removeOwnedRun, terminateOwned } from './lifecycle.mjs';
import { resolvePlaywright, runtimeError, sessionConfiguration } from './resolution.mjs';
import { executionDiagnostic } from './diagnostics.mjs';
export { recoverOwnedResources } from './lifecycle.mjs';

function abortError() { const error = runtimeError('ABORT_ERR', 'Browser execution was cancelled.'); error.name = 'AbortError'; return error; }

function validateTimeouts(options) {
  for (const name of ['startupTimeout', 'cleanupTimeout', 'timeout']) {
    const value = options[name];
    if (value === undefined || (name === 'timeout' && value === 0)) continue;
    if (!Number.isInteger(value) || value < 1 || value > 2147483647) throw runtimeError('INVALID_TIMEOUT', `${name} must be a positive integer in milliseconds.`, 'Use timeout:0 for a command without an execution deadline.');
  }
}

function boundedOutput(stream, limit = 1024 * 1024) {
  const chunks = [];
  let size = 0, truncated = false;
  stream?.on('data', chunk => {
    const remaining = Math.max(0, limit - size);
    if (remaining) { const kept = chunk.subarray(0, remaining); chunks.push(kept); size += kept.length; }
    if (chunk.length > remaining) truncated = true;
  });
  return () => ({ value: Buffer.concat(chunks, size).toString('utf8'), truncated });
}

async function supervised(configuration, options = {}) {
  if (options.signal?.aborted) throw abortError();
  const run = await createOwnedRun(options.resourceRoot, { temporaryRoot: options.temporaryRoot });
  const stdoutMode = options.stdio === 'inherit' ? 'inherit' : 'pipe';
  const child = fork(fileURLToPath(new URL('./supervisor.mjs', import.meta.url)), [], { detached: process.platform !== 'win32', stdio: [stdoutMode === 'inherit' ? 'inherit' : 'ignore', stdoutMode, stdoutMode, 'ipc'], env: { ...process.env, [OWNER_ENV]: run.record.token }, execArgv: [] });
  const stdout = boundedOutput(child.stdout, options.maxOutputBytes), stderr = boundedOutput(child.stderr, options.maxOutputBytes);
  let readyResolve, readyReject, resultResolve, resultReject, readySeen = false, resultSeen = false, closePromise, cleanupWarning;
  const ready = new Promise((resolve, reject) => { readyResolve = resolve; readyReject = reject; });
  const result = new Promise((resolve, reject) => { resultResolve = resolve; resultReject = reject; });
  // A session may never use the command-result promise. Keep a rejection
  // observed while preserving its value for command consumers.
  result.catch(() => {});
  ready.catch(() => {});
  const exit = new Promise(resolve => child.once('close', (exitCode, signal) => {
    const error = runtimeError('SUPERVISOR_EXITED', 'The browser supervisor stopped before completing the request.', 'Inspect the selected runtime and recover any remaining owned resources.');
    if (!readySeen) readyReject(error);
    if (!resultSeen) resultReject(error);
    resolve({ exitCode, signal });
  }));
  child.once('error', error => { readyReject(runtimeError('SUPERVISOR_START_FAILED', 'The browser supervisor could not start.', 'Check Node.js and the resource directory.', error)); resultReject(error); });
  child.on('message', message => {
    if (message.type === 'ready') { readySeen = true; readyResolve(message); }
    if (message.type === 'result') { resultSeen = true; resultResolve(message); }
    if (message.type === 'error') { const error = runtimeError(message.code, message.message, message.hint); readyReject(error); resultReject(error); }
    if (message.type === 'cleanup-warning') cleanupWarning = message;
  });
  const close = async () => {
    if (closePromise) return closePromise;
    closePromise = (async () => {
      options.signal?.removeEventListener('abort', onAbort);
      if (child.connected) child.send({ type: 'close' }, () => {});
      let timer;
      await Promise.race([exit, new Promise(resolve => { timer = setTimeout(resolve, options.cleanupTimeout ?? 7000); })]); clearTimeout(timer);
      if (child.exitCode === null && child.signalCode === null) {
        child.kill('SIGTERM');
        await Promise.race([exit, delay(1500)]);
      }
      if (child.exitCode === null && child.signalCode === null) { child.kill('SIGKILL'); await exit; }
      if (cleanupWarning?.code === 'PROVIDER_CLEANUP_FAILED') throw runtimeError('PROVIDER_CLEANUP_FAILED', cleanupWarning.message, 'Use the provider’s teardown/recovery operation with the retained session identity.');
      try { await terminateOwned(run.directory); await removeOwnedRun(run.directory); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    })();
    return closePromise;
  };
  const onAbort = () => { readyReject(abortError()); resultReject(abortError()); void close().catch(() => {}); };
  options.signal?.addEventListener('abort', onAbort, { once: true });
  try {
    run.record.supervisor = await processIdentity(child.pid);
    await atomicJSON(join(run.directory, 'ownership.json'), run.record);
    if (options.signal?.aborted) throw abortError();
    await new Promise((resolve, reject) => child.send({ type: 'start', configuration: { ...configuration, directory: run.directory } }, error => error ? reject(error) : resolve()));
    let timer;
    const startupTimeout = options.startupTimeout ?? 30000;
    try {
      const message = await Promise.race([ready, new Promise((_, reject) => { timer = setTimeout(() => reject(runtimeError('SESSION_START_TIMEOUT', 'Browser execution did not become ready before its startup deadline.', 'Check browser installation or adjust startupTimeout for this environment.')), startupTimeout); })]);
      return { ...message, result, close, exit, stdout, stderr, directory: run.directory };
    } finally { clearTimeout(timer); }
  } catch (error) { await close(); throw error; }
}

const directLeases = new Set();
const directSignalHandlers = new Map();
function trackDirectLease(close) {
  directLeases.add(close);
  if (!directSignalHandlers.size) for (const [signal, code] of [['SIGINT', 130], ['SIGTERM', 143], ['SIGHUP', 129]]) {
    const handler = async () => {
      const exitAfter = process.listenerCount(signal) === 1;
      await Promise.allSettled([...directLeases].map(close => close()));
      if (exitAfter) process.exit(code);
    };
    directSignalHandlers.set(signal, handler); process.on(signal, handler);
  }
  return () => {
    directLeases.delete(close);
    if (!directLeases.size) { for (const [signal, handler] of directSignalHandlers) process.removeListener(signal, handler); directSignalHandlers.clear(); }
  };
}

async function directProvider(options, configuration) {
  const lease = await acquireProvider({ ...options, ...configuration });
  let closing, untrack;
  const close = async () => {
    if (!closing) closing = (async () => { try { await lease.close(); } finally { untrack?.(); options.signal?.removeEventListener('abort', onAbort); } })();
    return closing;
  };
  const onAbort = () => { void close().catch(() => {}); };
  untrack = trackDirectLease(close);
  options.signal?.addEventListener('abort', onAbort, { once: true });
  if (options.signal?.aborted) { await close(); throw abortError(); }
  return { ...lease, close, info: { presentation: configuration.presentation, backend: lease.backend, hostOS: process.platform, renderingOS: lease.renderingOS, renderingOSSource: 'provider-declared', provider: { identity: lease.identity, capabilities: lease.capabilities }, cleanup: 'provider-lifecycle' } };
}

export async function openSession(options = {}) {
  validateTimeouts(options);
  if (options.signal?.aborted) throw abortError();
  const resolved = await resolvePlaywright(options);
  const configuration = sessionConfiguration(options, resolved);
  let guard, browser, context, page, closePromise, info, diagnosticPath, failure;
  const openedAt = new Date().toISOString();
  const diagnostic = async cleanup => {
    if (diagnosticPath) await atomicJSON(diagnosticPath, { type: 'playwright-session', openedAt, info: info ?? { hostOS: process.platform, playwrightVersion: resolved.version, browser: configuration.browser, presentation: configuration.presentation }, ...(failure ? { failure } : {}), cleanup });
  };
  if (options.artifactDir) {
    const directory = resolve(resolved.projectDir, options.artifactDir);
    await mkdir(directory, { recursive: true, mode: 0o700 });
    diagnosticPath = join(directory, `session-${randomUUID()}.json`);
    await diagnostic({ status: 'starting' });
  }
  const close = async () => {
    if (closePromise) return closePromise;
    closePromise = (async () => {
      const errors = [];
      try { if (context) await context.close(); } catch (error) { if (browser?.isConnected()) errors.push(error); }
      try { if (browser?.isConnected()) await browser.close(); } catch (error) { if (browser?.isConnected()) errors.push(error); }
      try { await guard?.close(); } catch (error) { errors.push(error); }
      await diagnostic({ status: errors.length ? 'incomplete' : 'completed', endedAt: new Date().toISOString() });
      if (errors.length) throw runtimeError('CLEANUP_INCOMPLETE', 'Browser cleanup is incomplete.', 'Inspect the retained receipt and recover the owned resource directory.', errors[0]);
    })();
    return closePromise;
  };
  try {
    const { contextOptions: _contextOptions, ...supervisorConfiguration } = configuration;
    guard = options.provider && typeof options.provider === 'object'
      ? await directProvider(options, configuration)
      : await supervised({ ...supervisorConfiguration, viewport: configuration.contextOptions.viewport, screen: configuration.contextOptions.screen, mode: 'session', modulePath: resolved.modulePath, projectDir: resolved.projectDir, provider: options.provider ? resolve(resolved.projectDir, options.provider) : undefined, providerOptions: options.providerOptions, artifactDir: options.artifactDir, diagnosticPath, startupTimeout: options.startupTimeout, xvfbPath: options.xvfbPath }, options);
    if (!guard.endpoint) throw runtimeError('PROVIDER_ENDPOINT', 'The session provider did not return a Playwright endpoint.', 'Return endpoint from browserType.launchServer().');
    browser = await resolved.playwright[configuration.browser].connect(guard.endpoint, { timeout: options.startupTimeout ?? 30000, ...options.connectOptions });
    context = await browser.newContext(configuration.contextOptions);
    page = await context.newPage();
    const observed = await page.evaluate(() => ({ layoutViewport: { width: innerWidth, height: innerHeight }, screen: { width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight }, deviceScaleFactor: devicePixelRatio, touchPoints: navigator.maxTouchPoints }));
    observed.viewport = page.viewportSize();
    observed.geometryAt = 'initial-about:blank';
    info = { ...guard.info, playwrightVersion: resolved.version, browser: configuration.browser, browserVersion: browser.version(), channel: configuration.launchOptions.channel ?? null, requested: { viewport: configuration.contextOptions.viewport, screen: configuration.contextOptions.screen ?? null, display: configuration.display }, observed, device: configuration.device, emulation: { isMobile: configuration.contextOptions.isMobile ?? false, hasTouch: configuration.contextOptions.hasTouch ?? false, deviceScaleFactor: configuration.contextOptions.deviceScaleFactor ?? 1, colorScheme: configuration.contextOptions.colorScheme ?? null, locale: configuration.contextOptions.locale ?? null, timezoneId: configuration.contextOptions.timezoneId ?? null }, ...(diagnosticPath ? { diagnosticPath } : {}) };
    await diagnostic({ status: 'open' });
    browser.once('disconnected', () => { void close().catch(() => {}); });
    if (options.signal?.aborted) throw abortError();
    return { browser, context, page, info, close };
  } catch (error) {
    failure = executionDiagnostic(error, { ...options, browser: configuration.browser, env: { ...process.env, ...options.env } });
    await close().catch(() => {});
    const sanitized = runtimeError(failure.code, failure.message, failure.hint);
    if (error?.name === 'AbortError') sanitized.name = 'AbortError';
    if (diagnosticPath) sanitized.diagnosticPath = diagnosticPath;
    throw sanitized;
  }
}

export async function withSession(options, fn) {
  const session = await openSession(options);
  try { return await fn(session); } finally { await session.close(); }
}

export async function inspectCapabilities(options = {}) {
  const diagnostics = [];
  let runtime;
  try { runtime = await resolvePlaywright(options); }
  catch (error) { diagnostics.push({ code: error.code, message: error.message, hint: error.hint }); }
  const xvfb = process.platform === 'linux' ? await findExecutable('Xvfb') : null;
  const powershell = process.platform === 'win32' ? await findExecutable('powershell.exe') ?? await findExecutable('pwsh.exe') : null;
  const engines = runtime?.engines.map(name => ({ name, executable: runtime.playwright[name].executablePath(), executableExists: existsSync(runtime.playwright[name].executablePath()) })) ?? [];
  const browserPresent = engines.some(engine => engine.executableExists);
  const backendPresent = !!options.provider || !!xvfb || !!powershell;
  const result = { nodeVersion: process.version, hostOS: process.platform, playwright: runtime ? { version: runtime.version, modulePath: runtime.modulePath, engines } : null, presentations: { headless: { available: !!runtime && browserPresent, backend: 'native-headless' }, isolatedHeaded: { available: !!runtime && backendPresent && (browserPresent || !!options.provider), backendAvailable: backendPresent, providerConfigured: !!options.provider, backend: options.provider ? 'configured-provider' : process.platform === 'linux' ? 'xvfb' : process.platform === 'win32' ? 'win32-private-desktop' : 'configured-provider', nativeQualification: process.platform === 'linux' ? 'run-local-checks' : 'pending' } }, diagnostics };
  if (runtime && !browserPresent && !options.provider) diagnostics.push({ code: 'BROWSER_EXECUTABLE_MISSING', message: 'No bundled Playwright browser executable is present.', hint: 'Install the browser required by the task with the selected Playwright version, or configure an existing channel/executable.' });
  if (process.platform === 'linux' && !xvfb && !options.provider) diagnostics.push({ code: 'XVFB_MISSING', message: 'Xvfb is unavailable for isolated headed execution.', hint: 'Install optional Xvfb or use headless.' });
  if (process.platform === 'darwin' && !options.provider) diagnostics.push({ code: 'ISOLATED_PROVIDER_REQUIRED', message: 'Isolated headed execution requires a configured native session provider.', hint: 'Supply provider or use headless.' });
  if (options.devices && runtime) result.devices = runtime.playwright.devices;
  return result;
}

export async function runIsolated(command, args = [], options = {}) {
  validateTimeouts(options);
  if (typeof command !== 'string' || !command || !Array.isArray(args) || args.some(arg => typeof arg !== 'string')) throw runtimeError('INVALID_COMMAND', 'Execution requires an executable and a string argument array.', 'Pass the command directly; shell syntax requires an explicit shell command.');
  const presentation = options.presentation ?? 'isolated-headed';
  if (!['headless', 'isolated-headed'].includes(presentation)) throw runtimeError('INVALID_PRESENTATION', 'Unknown command presentation.', 'Valid presentations: headless, isolated-headed.');
  const display = options.display ?? options.screen ?? { width: options.viewport?.width ?? 1280, height: options.viewport?.height ?? 900 };
  if (!Number.isInteger(display.width) || !Number.isInteger(display.height) || display.width < 1 || display.height < 1 || display.width > 32768 || display.height > 32768) throw runtimeError('INVALID_GEOMETRY', 'display requires positive integer width and height up to 32768.');
  const configuration = { mode: 'command', command, args, presentation, display, projectDir: resolve(options.projectDir ?? options.cwd ?? process.cwd()), cwd: resolve(options.cwd ?? options.projectDir ?? process.cwd()), env: options.env, providerOptions: options.providerOptions, timeout: options.timeout, startupTimeout: options.startupTimeout, xvfbPath: options.xvfbPath };
  const direct = options.provider && typeof options.provider === 'object';
  const guard = direct ? await directProvider(options, configuration) : await supervised({ ...configuration, provider: options.provider ? resolve(configuration.projectDir, options.provider) : undefined }, { stdio: 'inherit', ...options });
  let timer;
  try {
    if (direct && typeof guard.run !== 'function') throw runtimeError('PROVIDER_COMMAND', 'The configured provider does not expose run(command,args,options).');
    const completion = direct ? guard.run(command, args, { cwd: configuration.cwd, env: options.env, timeout: options.timeout, signal: options.signal }) : guard.result;
    const result = await (options.timeout ? Promise.race([completion, new Promise((_, reject) => { timer = setTimeout(() => reject(runtimeError('COMMAND_TIMEOUT', 'The command exceeded its execution deadline.', 'Inspect retained evidence and adjust the deadline if the task needs longer.')), options.timeout); })]) : completion);
    if (!result || (!Number.isInteger(result.exitCode) && !(result.exitCode === null && typeof result.signal === 'string'))) throw runtimeError('COMMAND_RESULT_INVALID', 'The command provider did not report an exit code or termination signal.', 'Return {exitCode,signal} from the provider’s run() method.');
    await guard.close();
    return { exitCode: result.exitCode, signal: result.signal ?? null, info: guard.info, ...(options.stdio === 'pipe' && !direct ? { stdout: guard.stdout().value, stderr: guard.stderr().value, outputTruncated: guard.stdout().truncated || guard.stderr().truncated } : {}) };
  } finally { clearTimeout(timer); await guard.close(); }
}
