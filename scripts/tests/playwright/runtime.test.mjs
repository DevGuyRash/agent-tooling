import test from 'node:test';
import assert from 'node:assert/strict';
import { fork, spawn, spawnSync } from 'node:child_process';
import { mkdtemp, mkdir, readFile, readdir, rm, symlink, writeFile, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { openSession, withSession, runIsolated, inspectCapabilities, recoverOwnedResources } from '../../../plugins/playwright-testing/runtime/session.mjs';
import { atomicJSON, createOwnedRun, delay, identityAlive, ownProcess, ownedLinuxProcesses, OWNER_ENV, processIdentity, readOwnedTemporary, removeOwnedRun } from '../../../plugins/playwright-testing/runtime/lifecycle.mjs';
import { resolvePlaywright } from '../../../plugins/playwright-testing/runtime/resolution.mjs';

const playwrightPath = process.env.PW_TEST_PLAYWRIGHT_PATH;
const native = !!playwrightPath;
const linux = native && process.platform === 'linux' && spawnSync('Xvfb', ['-help'], { stdio: 'ignore' }).status === 0;
const sessionModule = pathToFileURL(resolve(fileURLToPath(new URL('../../../plugins/playwright-testing/runtime/session.mjs', import.meta.url)))).href;
async function scratch(t) { const dir = await mkdtemp(join(tmpdir(), 'playwright-runtime-test-')); t.after(() => rm(dir, { recursive: true, force: true })); return dir; }
async function absent(path) { try { await access(path); return false; } catch (error) { if (error.code === 'ENOENT') return true; throw error; } }
async function eventually(predicate, message, timeout = 15000) { const deadline = Date.now() + timeout; while (Date.now() < deadline) { if (await predicate()) return; await delay(40); } assert.fail(message); }
function longResourceRoot(directory) { return join(directory, 'ordinary project space 雪', 'qualification evidence and retained reports', 'nested browser survey capture collection', 'owned execution resources'); }

test('resolves explicit and project-local packages from unrelated Unicode paths', { skip: !native }, async t => {
  const dir = await scratch(t), project = join(dir, 'project space 雪');
  await mkdir(join(project, 'node_modules'), { recursive: true });
  await symlink(playwrightPath, join(project, 'node_modules', 'playwright'), process.platform === 'win32' ? 'junction' : 'dir');
  const explicit = await resolvePlaywright({ projectDir: dir, playwrightPath });
  const found = await resolvePlaywright({ projectDir: project });
  assert.equal(found.version, explicit.version);
  assert.deepEqual(found.engines, explicit.engines);
  const capabilities = await inspectCapabilities({ projectDir: project, devices: true });
  assert.ok(Object.keys(capabilities.devices).length > 0);
  assert.equal(capabilities.playwright.engines.find(x => x.name === 'chromium').executableExists, true);
});

test('missing setup and invalid choices report actionable diagnostics', async t => {
  const dir = await scratch(t);
  const capabilities = await inspectCapabilities({ projectDir: dir });
  assert.equal(capabilities.playwright, null);
  assert.equal(capabilities.diagnostics[0].code, 'PLAYWRIGHT_NOT_FOUND');
  assert.ok(capabilities.diagnostics[0].hint);
  await assert.rejects(runIsolated('node', [], { presentation: 'mystery' }), { code: 'INVALID_PRESENTATION' });
  await assert.rejects(runIsolated('node', [], { startupTimeout: Infinity }), { code: 'INVALID_TIMEOUT' });
  await assert.rejects(resolvePlaywright({ projectDir: join(dir, 'missing') }), { code: 'PROJECT_DIRECTORY' });
  if (process.platform !== 'win32') {
    const resourceRoot = join(dir, 'long-temporary-option-resources');
    await assert.rejects(createOwnedRun(resourceRoot, { temporaryRoot: longResourceRoot(dir) }), error => error.code === 'TEMPORARY_PATH_TOO_LONG' && /temporaryRoot/.test(error.hint));
    assert.deepEqual(await readdir(resourceRoot), []);
  }
  if (native) {
    await assert.rejects(openSession({ playwrightPath, browser: 'imaginary' }), { code: 'UNKNOWN_BROWSER' });
    await assert.rejects(openSession({ playwrightPath, device: 'imaginary' }), { code: 'UNKNOWN_DEVICE' });
    await assert.rejects(openSession({ playwrightPath, launchOptions: { headless: false } }), { code: 'PRESENTATION_CONFLICT' });
  }
});

test('headless sessions expose normal Playwright objects and actual geometry', { skip: !native }, async t => {
  const dir = await scratch(t), resources = join(dir, 'resources');
  const runtime = await resolvePlaywright({ playwrightPath });
  const device = Object.keys(runtime.playwright.devices).find(name => runtime.playwright.devices[name].defaultBrowserType === 'chromium' && runtime.playwright.devices[name].isMobile);
  let session;
  try {
    session = await openSession({ playwrightPath, resourceRoot: resources, artifactDir: join(dir, 'evidence'), device, browser: 'chromium', contextOptions: { viewport: { width: 400, height: 600 }, deviceScaleFactor: 1.5, locale: 'en-GB', extraHTTPHeaders: { Authorization: 'fixture-secret-value' } }, launchOptions: { env: { ...process.env, TEST_SURVEY_SECRET: 'fixture-secret-value' } }, viewport: { width: 512, height: 640 } });
    await session.page.setContent('<label>Name <input></label><button>Send</button><output></output><script>document.querySelector("button").onclick=()=>document.querySelector("output").textContent=document.querySelector("input").value</script>');
    await session.page.getByRole('textbox', { name: 'Name' }).fill('runtime works');
    await session.page.getByRole('button', { name: 'Send' }).click();
    assert.equal(await session.page.locator('output').textContent(), 'runtime works');
    const png = await session.page.screenshot();
    assert.equal(png.readUInt32BE(16), 768);
    assert.equal(png.readUInt32BE(20), 960);
    assert.equal(session.info.backend, 'native-headless');
    assert.equal(session.info.renderingOSSource, 'native-runtime');
    assert.deepEqual(session.info.observed.viewport, { width: 512, height: 640 });
    assert.equal(session.info.observed.deviceScaleFactor, 1.5);
    assert.equal(session.info.device, device);
    assert.ok(session.info.browserVersion);
    const temporary = await readdir(session.info.temporaryDirectory);
    assert.ok(temporary.some(name => name.startsWith('playwright_chromiumdev_profile-')), 'browser profile must be inside the associated owned temporary directory');
  } finally { await session?.close(); }
  assert.equal(session.browser.isConnected(), false);
  assert.equal(await absent(session.info.temporaryDirectory), true);
  const receiptBytes = await readFile(session.info.diagnosticPath, 'utf8');
  assert.equal(JSON.parse(receiptBytes).cleanup.status, 'completed');
  assert.equal(JSON.parse(receiptBytes).info.browserVersion, session.info.browserVersion);
  assert.equal(receiptBytes.includes('fixture-secret-value'), false);
  assert.deepEqual(await readdir(resources), []);
});

test('long Unicode and spaced resource roots support native browser interaction and screenshots', { skip: !native }, async t => {
  const dir = await scratch(t), resourceRoot = longResourceRoot(dir);
  assert.ok(Buffer.byteLength(resourceRoot) > 150);
  for (const presentation of linux ? ['headless', 'isolated-headed'] : ['headless']) {
    const session = await openSession({ playwrightPath, resourceRoot, artifactDir: join(resourceRoot, '..', 'retained evidence'), presentation, viewport: { width: 640, height: 480 } });
    try {
      await session.page.setContent('<title>Long-path fixture</title><button>Reveal evidence</button><output></output><script>document.querySelector("button").onclick=()=>document.querySelector("output").textContent="Available"</script>');
      await session.page.getByRole('button', { name: 'Reveal evidence' }).click();
      assert.equal(await session.page.locator('output').textContent(), 'Available');
      const png = await session.page.screenshot();
      assert.equal(png.readUInt32BE(16), 640);
      assert.equal(png.readUInt32BE(20), 480);
      const owner = JSON.parse(await readFile(join(session.info.resourceDirectory, 'ownership.json'), 'utf8'));
      assert.equal(await readOwnedTemporary(session.info.resourceDirectory, owner), session.info.temporaryDirectory);
      assert.equal(session.info.temporaryDirectory.startsWith(resourceRoot), false);
    } finally { await session.close(); }
    assert.equal(await absent(session.info.resourceDirectory), true);
    assert.equal(await absent(session.info.temporaryDirectory), true);
    assert.equal(JSON.parse(await readFile(session.info.diagnosticPath, 'utf8')).cleanup.status, 'completed');
  }
  assert.deepEqual(await readdir(resourceRoot), []);
});

test('private Linux display requires its cookie and owns popup windows', { skip: !linux }, async t => {
  const dir = await scratch(t);
  const session = await openSession({ playwrightPath, resourceRoot: join(dir, 'resources'), presentation: 'isolated-headed', viewport: { width: 640, height: 480 }, launchOptions: { env: { ...process.env, WAYLAND_DISPLAY: 'unrelated-wayland', WAYLAND_SOCKET: '999' } } });
  t.after(() => session.close());
  const display = session.info.display, authority = join(session.info.resourceDirectory, 'Xauthority');
  assert.equal(session.info.backend, 'xvfb');
  assert.equal((await readFile(authority)).readUInt16BE(0), 65535);
  const allowed = spawnSync('xdpyinfo', ['-display', display], { encoding: 'utf8', env: { ...process.env, XAUTHORITY: authority } });
  assert.equal(allowed.status, 0, allowed.stderr);
  assert.match(allowed.stdout, /dimensions:\s+672x608 pixels/);
  const denied = spawnSync('xdpyinfo', ['-display', display], { encoding: 'utf8', env: { ...process.env, XAUTHORITY: join(dir, 'no-cookie') } });
  assert.notEqual(denied.status, 0);
  await session.page.setContent('<title>Runtime main</title><button onclick="window.open(\'about:blank\',\'runtime-popup\',\'popup,width=350,height=260\')">Open detail</button>');
  const popupPromise = session.page.waitForEvent('popup');
  await session.page.getByRole('button', { name: 'Open detail' }).click();
  const popup = await popupPromise;
  await popup.setContent('<title>Runtime popup</title><label>Detail <input></label>');
  await popup.getByRole('textbox', { name: 'Detail' }).fill('private input');
  assert.equal(await popup.getByRole('textbox').inputValue(), 'private input');
  let windows;
  await eventually(() => {
    windows = spawnSync('xwininfo', ['-display', display, '-root', '-tree'], { encoding: 'utf8', env: { ...process.env, XAUTHORITY: authority } });
    return windows.status === 0 && /Runtime popup/.test(windows.stdout);
  }, 'popup window not observed on the private display');
  assert.ok((await popup.screenshot()).length > 1000);
  await session.close();
  assert.equal(await absent(session.info.resourceDirectory), true);
  assert.equal(await absent(`/tmp/.X11-unix/X${display.slice(1)}`), true);
  assert.equal(await absent(`/tmp/.X${display.slice(1)}-lock`), true);
});

test('concurrent private displays stay separate and close independently', { skip: !linux }, async t => {
  const dir = await scratch(t);
  const options = { playwrightPath, resourceRoot: join(dir, 'resources'), presentation: 'isolated-headed', viewport: { width: 500, height: 400 } };
  const sessions = await Promise.all([openSession(options), openSession(options)]);
  t.after(() => Promise.all(sessions.map(session => session.close())));
  assert.notEqual(sessions[0].info.display, sessions[1].info.display);
  await sessions[0].close();
  await sessions[1].page.setContent('<h1>Still running</h1>');
  assert.equal(await sessions[1].page.getByRole('heading').textContent(), 'Still running');
  await sessions[1].page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.ok((await sessions[1].page.screenshot()).length > 1000);
  await sessions[1].close();
  assert.deepEqual(await readdir(join(dir, 'resources')), []);
});

test('command wrapper preserves argv/cwd, applies child X11 environment, and returns exit code', { skip: !linux }, async t => {
  const dir = await scratch(t), cwd = join(dir, 'working space 雪');
  await mkdir(cwd);
  const args = ['space value', 'quote"value', '$HOME', 'semi;literal'];
  const result = await runIsolated(process.execPath, ['-e', 'console.log(JSON.stringify({args:process.argv.slice(1),cwd:process.cwd(),display:process.env.DISPLAY,wayland:process.env.WAYLAND_DISPLAY,socket:process.env.WAYLAND_SOCKET,kind:process.env.XDG_SESSION_TYPE,custom:process.env.RUNTIME_CUSTOM}));process.exitCode=7', ...args], { resourceRoot: join(dir, 'resources'), cwd, stdio: 'pipe', env: { WAYLAND_DISPLAY: 'host-wayland', WAYLAND_SOCKET: '9', RUNTIME_CUSTOM: 'kept' } });
  assert.equal(result.exitCode, 7);
  const observed = JSON.parse(result.stdout);
  assert.deepEqual(observed.args, args);
  assert.equal(observed.cwd, cwd);
  assert.equal(observed.display, result.info.display);
  assert.equal(observed.wayland, undefined);
  assert.equal(observed.socket, undefined);
  assert.equal(observed.kind, 'x11');
  assert.equal(observed.custom, 'kept');
  assert.deepEqual(await readdir(join(dir, 'resources')), []);
});

test('failure, startup failure, timeout, and abort close owned resources', { skip: !native }, async t => {
  const dir = await scratch(t), resourceRoot = join(dir, 'resources');
  await assert.rejects(withSession({ playwrightPath, resourceRoot }, async () => { throw new Error('fixture failure'); }), /fixture failure/);
  assert.deepEqual(await readdir(resourceRoot), []);
  if (linux) {
    await assert.rejects(openSession({ playwrightPath, resourceRoot, presentation: 'isolated-headed', xvfbPath: join(dir, 'missing-Xvfb'), startupTimeout: 3000 }), { code: 'XVFB_START_FAILED' });
    assert.deepEqual(await readdir(resourceRoot), []);
  }
  await assert.rejects(runIsolated(process.execPath, ['-e', 'setInterval(()=>{},1000)'], { presentation: 'headless', resourceRoot, timeout: 100, stdio: 'pipe' }), { code: 'COMMAND_TIMEOUT' });
  assert.deepEqual(await readdir(resourceRoot), []);
  const abort = new AbortController();
  const session = await openSession({ playwrightPath, resourceRoot, signal: abort.signal });
  abort.abort();
  await eventually(() => absent(session.info.resourceDirectory), 'aborted session still owns resources');
  assert.equal(session.browser.isConnected(), false);
  await session.close();
});

test('normal command exit reaps detached descendants owned by this run', { skip: !linux }, async t => {
  const dir = await scratch(t), pidFile = join(dir, 'pid.json');
  const script = 'const {spawn}=require("node:child_process");const {writeFileSync}=require("node:fs");const child=spawn(process.execPath,["-e","setInterval(()=>{},1000)"],{detached:true,stdio:"ignore"});writeFileSync(process.argv[1],String(child.pid));child.unref()';
  const result = await runIsolated(process.execPath, ['-e', script, pidFile], { presentation: 'headless', stdio: 'pipe', resourceRoot: join(dir, 'resources') });
  assert.equal(result.exitCode, 0);
  const pid = Number(await readFile(pidFile, 'utf8'));
  await eventually(async () => !await processIdentity(pid), 'detached owned descendant survived completion');
});

test('supervisor removes browser/display resources when its parent is killed', { skip: !linux }, async t => {
  const dir = await scratch(t), fixture = join(dir, 'parent.mjs'), resourceRoot = longResourceRoot(dir);
  await writeFile(fixture, `import {openSession} from ${JSON.stringify(sessionModule)}; const s=await openSession({playwrightPath:process.env.PW_TEST_PLAYWRIGHT_PATH,resourceRoot:process.argv[2],artifactDir:process.argv[3],presentation:'isolated-headed'}); process.send({info:s.info}); setInterval(()=>{},1000);`);
  const child = fork(fixture, [resourceRoot, join(dir, 'evidence')], { env: { ...process.env, PW_TEST_PLAYWRIGHT_PATH: playwrightPath }, stdio: ['ignore', 'ignore', 'pipe', 'ipc'], execArgv: [] });
  t.after(() => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); });
  const info = await new Promise((resolve, reject) => { child.once('message', message => resolve(message.info)); child.once('error', reject); child.once('exit', code => reject(new Error(`fixture exited ${code}`))); });
  const record = JSON.parse(await readFile(join(info.resourceDirectory, 'ownership.json'), 'utf8'));
  child.kill('SIGKILL');
  await eventually(() => absent(info.resourceDirectory), 'orphan supervisor did not remove resources');
  assert.deepEqual(await ownedLinuxProcesses(record.token), []);
  assert.equal(await absent(info.temporaryDirectory), true);
  assert.equal(await absent(`/tmp/.X11-unix/X${info.display.slice(1)}`), true);
  await eventually(async () => JSON.parse(await readFile(info.diagnosticPath, 'utf8')).cleanup.status === 'completed', 'orphan cleanup did not update its retained receipt');
});

test('cancellation during provider acquisition closes without creating later resources', { skip: !native }, async t => {
  const dir = await scratch(t), providerPath = join(dir, 'slow-provider.mjs'), marker = join(dir, 'acquiring'), resourceRoot = join(dir, 'resources');
  await writeFile(providerPath, `import {writeFile} from 'node:fs/promises'; export async function acquire(options){await writeFile(options.providerOptions.marker,'acquiring');await new Promise(resolve=>{if(options.signal.aborted)resolve();else options.signal.addEventListener('abort',resolve,{once:true})});throw Object.assign(new Error('fixture cancelled'),{code:'ABORT_ERR'})}`);
  const controller = new AbortController();
  const pending = openSession({ playwrightPath, resourceRoot, provider: providerPath, providerOptions: { marker }, signal: controller.signal });
  pending.catch(() => {});
  await eventually(async () => !await absent(marker), 'provider did not start acquisition');
  controller.abort();
  await assert.rejects(pending, { code: 'ABORT_ERR' });
  assert.deepEqual(await readdir(resourceRoot), []);
});

test('recovery reclaims an actual browser and profile after both controller processes die', { skip: !linux }, async t => {
  const dir = await scratch(t), fixture = join(dir, 'orphan.mjs'), resourceRoot = longResourceRoot(dir);
  await writeFile(fixture, `import {openSession} from ${JSON.stringify(sessionModule)}; const s=await openSession({playwrightPath:process.env.PW_TEST_PLAYWRIGHT_PATH,resourceRoot:process.argv[2],presentation:'isolated-headed'}); process.send({info:s.info}); setInterval(()=>{},1000);`);
  const child = fork(fixture, [resourceRoot], { env: { ...process.env, PW_TEST_PLAYWRIGHT_PATH: playwrightPath }, stdio: ['ignore', 'ignore', 'pipe', 'ipc'], execArgv: [] });
  t.after(() => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); });
  const info = await new Promise((resolve, reject) => { child.once('message', message => resolve(message.info)); child.once('error', reject); child.once('exit', code => reject(new Error(`fixture exited ${code}`))); });
  const record = JSON.parse(await readFile(join(info.resourceDirectory, 'ownership.json'), 'utf8'));
  child.kill('SIGSTOP');
  process.kill(record.supervisor.pid, 'SIGKILL');
  child.kill('SIGKILL');
  await eventually(async () => !await identityAlive(record.owner) && !await identityAlive(record.supervisor), 'controller processes did not exit');
  const recovery = await recoverOwnedResources(resourceRoot);
  assert.ok(recovery.recovered.includes(record.id));
  await eventually(async () => (await ownedLinuxProcesses(record.token)).length === 0, 'browser descendants survived orphan recovery');
  assert.equal(await absent(info.resourceDirectory), true);
  assert.equal(await absent(info.temporaryDirectory), true);
  assert.equal(await absent(`/tmp/.X11-unix/X${info.display.slice(1)}`), true);
});

test('recovery is ownership-limited, detects live owners, and supports a read-only dry run', { skip: process.platform !== 'linux' }, async t => {
  const dir = await scratch(t), resourceRoot = join(dir, 'resources');
  const active = await createOwnedRun(resourceRoot);
  const abandoned = await createOwnedRun(resourceRoot);
  t.after(() => Promise.all([active, abandoned].map(run => rm(run.record.temporaryDirectory, { recursive: true, force: true }))));
  const unowned = spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], { stdio: 'ignore' });
  const owned = spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], { stdio: 'ignore', env: { ...process.env, [OWNER_ENV]: abandoned.record.token } });
  t.after(() => { unowned.kill(); owned.kill(); });
  await ownProcess(abandoned.directory, { pid: owned.pid, kind: 'fixture' });
  const record = JSON.parse(await readFile(join(abandoned.directory, 'ownership.json'), 'utf8'));
  record.owner = { pid: process.pid, started: 'not-the-current-process-start' };
  record.resources.push({ pid: unowned.pid, started: 'reused-pid', kind: 'fixture' });
  await atomicJSON(join(abandoned.directory, 'ownership.json'), record);
  await mkdir(join(resourceRoot, 'run-foreign'), { mode: 0o700 });
  await writeFile(join(resourceRoot, 'run-foreign', 'keep.txt'), 'unrelated');
  const before = await readFile(join(abandoned.directory, 'ownership.json'));
  const dry = await recoverOwnedResources(resourceRoot, { dryRun: true });
  assert.deepEqual(dry.wouldRecover, [abandoned.record.id]);
  assert.ok(dry.active.includes(active.record.id));
  assert.ok(await processIdentity(owned.pid));
  assert.deepEqual(await readFile(join(abandoned.directory, 'ownership.json')), before);
  const actual = await recoverOwnedResources(resourceRoot);
  assert.ok(actual.recovered.includes(abandoned.record.id));
  assert.ok(actual.skipped.some(entry => entry.id === 'run-foreign'));
  assert.ok(await processIdentity(unowned.pid));
  assert.equal(await readFile(join(resourceRoot, 'run-foreign', 'keep.txt'), 'utf8'), 'unrelated');
  assert.equal(await absent(active.directory), false);
  assert.equal(await absent(active.record.temporaryDirectory), false);
  assert.equal(await absent(abandoned.record.temporaryDirectory), true);
  await eventually(async () => !await processIdentity(owned.pid), 'owned process survived recovery');
  await removeOwnedRun(active.directory);
});

test('separate temporary storage cleanup requires matching reciprocal ownership', async t => {
  const dir = await scratch(t), run = await createOwnedRun(join(dir, 'resources'));
  t.after(() => rm(run.record.temporaryDirectory, { recursive: true, force: true }));
  const markerPath = join(run.record.temporaryDirectory, '.playwright-survey-owner.json');
  const original = await readFile(markerPath, 'utf8');
  await writeFile(join(run.record.temporaryDirectory, 'keep.txt'), 'preserve until ownership is resolved');
  await writeFile(markerPath, JSON.stringify({ ...JSON.parse(original), token: 'different-owner' }));
  await assert.rejects(removeOwnedRun(run.directory), { code: 'TEMPORARY_OWNERSHIP' });
  assert.equal(await readFile(join(run.record.temporaryDirectory, 'keep.txt'), 'utf8'), 'preserve until ownership is resolved');
  assert.equal(await absent(join(run.directory, 'ownership.json')), false);
  await writeFile(markerPath, original);
  await removeOwnedRun(run.directory);
  assert.equal(await absent(run.record.temporaryDirectory), true);
});

test('configured module providers retain identity and invoke owned teardown', { skip: !native }, async t => {
  const dir = await scratch(t), providerPath = join(dir, 'provider.mjs'), marker = join(dir, 'closed');
  await writeFile(providerPath, `import {createRequire} from 'node:module'; import {writeFile} from 'node:fs/promises'; const require=createRequire(import.meta.url); export async function acquire(options){const p=require(process.env.PW_TEST_PLAYWRIGHT_PATH);const server=await p.chromium.launchServer({headless:true,channel:'chromium',chromiumSandbox:true});return {identity:'fixture-owned-session',renderingOS:process.platform,capabilities:{isolated:true,headed:false},endpoint:server.wsEndpoint(),close:async()=>{await server.close();await writeFile(options.providerOptions.marker,'closed');if(options.providerOptions.failClose)throw new Error('fixture teardown failed')}}}`);
  const session = await openSession({ playwrightPath, resourceRoot: join(dir, 'resources'), provider: providerPath, providerOptions: { marker } });
  assert.equal(session.info.backend, 'configured-provider');
  assert.equal(session.info.renderingOSSource, 'provider-declared');
  assert.equal(session.info.provider.identity, 'fixture-owned-session');
  await session.page.setContent('<h1>Provider context</h1>');
  assert.equal(await session.page.getByRole('heading').textContent(), 'Provider context');
  await session.close();
  assert.equal(await readFile(marker, 'utf8'), 'closed');
  assert.deepEqual(await readdir(join(dir, 'resources')), []);
  const failing = await openSession({ playwrightPath, resourceRoot: join(dir, 'resources'), artifactDir: join(dir, 'evidence'), provider: providerPath, providerOptions: { marker, failClose: true } });
  await assert.rejects(failing.close(), { code: 'CLEANUP_INCOMPLETE' });
  const retained = JSON.parse(await readFile(join(failing.info.resourceDirectory, 'ownership.json'), 'utf8'));
  assert.equal(retained.cleanup.status, 'incomplete');
  assert.equal(retained.provider.identity, 'fixture-owned-session');
  assert.equal(JSON.parse(await readFile(failing.info.diagnosticPath, 'utf8')).cleanup.status, 'incomplete');
  // The fixture closed its real server before deliberately reporting failure.
  await removeOwnedRun(failing.info.resourceDirectory);
});

test('invalid provider capability still releases its lease', { skip: !native }, async () => {
  let closed = 0;
  const provider = { async acquire() { return { identity: 'fixture', renderingOS: 'fixture-os', capabilities: { isolated: false, headed: true }, close: async () => { closed++; } }; } };
  await assert.rejects(openSession({ playwrightPath, presentation: 'isolated-headed', provider }), { code: 'PROVIDER_ISOLATION' });
  assert.equal(closed, 1);
});

test('a command provider cannot silently report success without its execution result', async () => {
  let closed = 0;
  const provider = { async acquire() { return { identity: 'command-fixture', renderingOS: 'fixture-os', capabilities: {}, run: async () => ({}), close: async () => { closed++; } }; } };
  await assert.rejects(runIsolated('fixture-command', [], { presentation: 'headless', provider }), { code: 'COMMAND_RESULT_INVALID' });
  assert.equal(closed, 1);
});

test('captured command output reports its bounded truncation', async t => {
  const dir = await scratch(t);
  const result = await runIsolated(process.execPath, ['-e', 'process.stdout.write("x".repeat(512))'], { presentation: 'headless', resourceRoot: join(dir, 'resources'), stdio: 'pipe', maxOutputBytes: 40 });
  assert.equal(result.stdout, 'x'.repeat(40));
  assert.equal(result.outputTruncated, true);
  assert.equal(result.exitCode, 0);
});
