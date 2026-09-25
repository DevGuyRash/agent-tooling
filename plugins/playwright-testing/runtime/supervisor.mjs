import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { acquireXvfb, x11Environment } from './platforms/linux.mjs';
import { acquireProvider } from './platforms/provider.mjs';
import { acquireWindowsWorker } from './platforms/windows.mjs';
import { atomicJSON, ownProcess, OWNER_ENV, readOwnedRun, readOwnedTemporary, removeOwnedRun, terminateOwned } from './lifecycle.mjs';
import { resolvePlaywright, runtimeError } from './resolution.mjs';
import { executionDiagnostic } from './diagnostics.mjs';

let configuration, lease, server, command, closing, controlTimer;
const acquisitions = new Set();
const abort = new AbortController();

async function acquire(action, assign) {
  const operation = action().then(value => { assign(value); return value; });
  acquisitions.add(operation);
  try { return await operation; } finally { acquisitions.delete(operation); }
}

async function send(message) {
  if (configuration?.privateWorker) {
    await atomicJSON(join(configuration.directory, message.type === 'result' ? 'windows-result.json' : 'windows-ready.json'), message);
  } else if (process.connected) {
    await new Promise(resolve => process.send(message, () => resolve()));
  }
}

async function close() {
  if (closing) return closing;
  closing = (async () => {
    abort.abort();
    clearInterval(controlTimer);
    await Promise.allSettled([...acquisitions]);
    let providerCleanupFailed = false;
    if (server) await server.close().catch(() => {});
    if (command && command.exitCode === null && command.signalCode === null) {
      try { command.kill('SIGTERM'); } catch { /* Command already exited. */ }
    }
    if (lease) await lease.close().catch(() => { if (configuration?.provider) providerCleanupFailed = true; });
    if (configuration && !configuration.privateWorker) {
      let completed = false;
      try {
        await terminateOwned(configuration.directory);
        if (providerCleanupFailed) {
          const record = await readOwnedRun(configuration.directory);
          record.cleanup = { status: 'incomplete', reason: 'provider teardown failed' };
          await atomicJSON(join(configuration.directory, 'ownership.json'), record);
          await send({ type: 'cleanup-warning', code: 'PROVIDER_CLEANUP_FAILED', message: 'The session provider did not complete teardown; its identity remains in the ownership record.' });
        } else { await removeOwnedRun(configuration.directory); completed = true; }
      } catch (error) { if (error.code !== 'ENOENT') await send({ type: 'cleanup-warning', message: 'Owned resource cleanup is incomplete; use recoverOwnedResources on the resource root.' }); }
      if (configuration.diagnosticPath) {
        try {
          const receipt = JSON.parse(await readFile(configuration.diagnosticPath, 'utf8'));
          await atomicJSON(configuration.diagnosticPath, { ...receipt, cleanup: { status: completed ? 'completed' : 'incomplete', endedAt: new Date().toISOString() } });
        } catch { /* Parent retains its receipt when diagnostic storage fails. */ }
      }
    }
  })();
  return closing;
}

async function shutdown(code = 0) { await close(); process.exit(code); }
process.on('disconnect', () => { void shutdown(); });
for (const signal of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.on(signal, () => { void shutdown(); });
process.on('message', message => { if (message?.type === 'close') void shutdown(); });

async function run(configurationInput) {
  configuration = configurationInput;
  const record = await readOwnedRun(configuration.directory);
  const temporary = await readOwnedTemporary(configuration.directory, record);
  // Playwright creates profiles through os.tmpdir(). Scope that directory to
  // this supervisor and its children; the user's process environment stays intact.
  process.env.TMPDIR = temporary;
  if (process.platform === 'win32') { process.env.TEMP = temporary; process.env.TMP = temporary; }
  const environment = { ...process.env, ...configuration.env, [OWNER_ENV]: record.token };
  environment.TMPDIR = temporary;
  if (process.platform === 'win32') { environment.TEMP = temporary; environment.TMP = temporary; }
  const baseInfo = { presentation: configuration.presentation, hostOS: process.platform, renderingOS: process.platform, renderingOSSource: 'native-runtime', backend: 'native-headless', resourceDirectory: configuration.directory, temporaryDirectory: temporary };
  if (configuration.privateWorker) {
    baseInfo.backend = 'win32-private-desktop';
    controlTimer = setInterval(async () => {
      try { if (JSON.parse(await readFile(join(configuration.directory, 'windows-control.json'), 'utf8')).close) void shutdown(); } catch { /* No teardown requested yet. */ }
    }, 75);
  }
  if (configuration.provider) {
    await acquire(() => acquireProvider({ ...configuration, env: undefined, signal: abort.signal }), value => { lease = value; });
    if (closing) return;
    baseInfo.backend = lease.backend;
    baseInfo.renderingOS = lease.renderingOS;
    baseInfo.renderingOSSource = 'provider-declared';
    baseInfo.provider = { identity: lease.identity, capabilities: lease.capabilities };
    const ownership = await readOwnedRun(configuration.directory);
    ownership.provider = { module: configuration.provider, identity: lease.identity, renderingOS: lease.renderingOS };
    await atomicJSON(join(configuration.directory, 'ownership.json'), ownership);
  } else if (configuration.presentation === 'isolated-headed' && !configuration.privateWorker) {
    if (process.platform === 'linux') {
      await acquire(() => acquireXvfb({ directory: configuration.directory, env: environment, display: configuration.display, timeout: configuration.startupTimeout, executable: configuration.xvfbPath }), value => { lease = value; });
      if (closing) return;
      Object.assign(baseInfo, lease.info, { backend: lease.backend });
    } else if (process.platform === 'win32') {
      await acquire(() => acquireWindowsWorker({ directory: configuration.directory, env: environment, options: { ...configuration, token: record.token } }), value => { lease = value; });
      if (closing) return;
      await send({ type: 'ready', endpoint: lease.endpoint, info: { ...baseInfo, ...lease.info, backend: lease.backend, renderingOS: lease.renderingOS } });
      if (configuration.mode === 'command') { await send(await lease.completion()); await shutdown(); }
      return;
    } else {
      throw runtimeError('ISOLATED_PROVIDER_REQUIRED', 'Isolated headed execution requires a configured native session provider on this platform.', 'Supply provider, or select headless. See the platform execution reference.');
    }
  }
  const env = lease?.env ?? environment;
  if (configuration.mode === 'session') {
    if (lease?.endpoint) {
      await send({ type: 'ready', endpoint: lease.endpoint, info: baseInfo });
      return;
    }
    if (configuration.provider) throw runtimeError('PROVIDER_ENDPOINT', 'The session provider did not return a Playwright endpoint.', 'Return endpoint from browserType.launchServer(), using the compatible Playwright version.');
    const { playwright } = await resolvePlaywright({ playwrightPath: configuration.modulePath, projectDir: configuration.projectDir });
    const launchOptions = { ...configuration.launchOptions, env: { ...env, ...configuration.launchOptions?.env, [OWNER_ENV]: record.token } };
    launchOptions.env.TMPDIR = temporary;
    if (process.platform === 'win32') { launchOptions.env.TEMP = temporary; launchOptions.env.TMP = temporary; }
    if (lease?.backend === 'xvfb') {
      launchOptions.env = x11Environment(launchOptions.env, { display: lease.env.DISPLAY, authority: lease.env.XAUTHORITY });
      if (configuration.browser === 'chromium') launchOptions.args = [...(launchOptions.args ?? []).filter(arg => !arg.startsWith('--ozone-platform=') && !arg.startsWith('--display=')), '--ozone-platform=x11'];
    }
    if (closing) return;
    await acquire(() => playwright[configuration.browser].launchServer(launchOptions), value => { server = value; });
    if (closing) return;
    await ownProcess(configuration.directory, { pid: server.process().pid, kind: 'browser-server', group: true });
    server.on('close', () => { if (!closing) void shutdown(); });
    await send({ type: 'ready', endpoint: server.wsEndpoint(), info: baseInfo });
  } else if (configuration.mode === 'command') {
    await send({ type: 'ready', info: baseInfo });
    if (lease?.run) {
      const result = await lease.run(configuration.command, configuration.args, { cwd: configuration.cwd, env: configuration.env, timeout: configuration.timeout });
      await send({ type: 'result', ...result });
      await shutdown();
      return;
    }
    if (configuration.provider) throw runtimeError('PROVIDER_COMMAND', 'The configured provider does not expose run(command,args,options).', 'Use its browser session endpoint, or supply a provider with command execution.');
    command = spawn(configuration.command, configuration.args, { cwd: configuration.cwd, env, detached: process.platform !== 'win32', stdio: 'inherit', windowsHide: true });
    const completion = new Promise((resolve, reject) => {
      command.once('error', error => reject(runtimeError('COMMAND_START_FAILED', 'The requested command could not start.', 'Check the executable and working directory.', error)));
      command.once('exit', (exitCode, signal) => resolve({ exitCode, signal }));
    });
    completion.catch(() => {});
    await ownProcess(configuration.directory, { pid: command.pid, kind: 'command', group: process.platform !== 'win32' });
    const result = await completion;
    await send({ type: 'result', ...result });
    await shutdown();
  }
}

async function start(configuration) {
  try { await run(configuration); }
  catch (error) {
    const failure = executionDiagnostic(error, { ...configuration, env: { ...process.env, ...configuration.env } });
    if (configuration.diagnosticPath) {
      try {
        const receipt = JSON.parse(await readFile(configuration.diagnosticPath, 'utf8'));
        await atomicJSON(configuration.diagnosticPath, { ...receipt, failure });
      } catch { /* Preserve the primary error if retained diagnostics are unavailable. */ }
    }
    await send({ type: 'error', ...failure });
    await shutdown(1);
  }
}

if (process.argv[2] === '--private-worker') {
  await start(JSON.parse(await readFile(process.argv[3], 'utf8')));
} else {
  process.once('message', message => { if (message?.type === 'start') void start(message.configuration); });
}
