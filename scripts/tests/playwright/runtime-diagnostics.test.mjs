import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { executionDiagnostic } from '../../../plugins/playwright-testing/runtime/diagnostics.mjs';
import { openSession } from '../../../plugins/playwright-testing/runtime/session.mjs';

const upstreamDependencies = `browserType.launchServer:
╔══════════════════════════════════════════════════════╗
║ Host system is missing dependencies to run browsers. ║
║ Please install them with the following command:      ║
║     sudo npx playwright install-deps                 ║
║ Alternatively, use apt:                             ║
║     sudo apt-get install libicu74\\                  ║
║         libflite1                                   ║
╚══════════════════════════════════════════════════════╝
    at validateDependenciesLinux (/fixture/lib/coreBundle.js:32259:9)`;

test('upstream missing-package and shared-library causes remain actionable', () => {
  const result = executionDiagnostic(new Error(upstreamDependencies), { browser: 'webkit' });
  assert.equal(result.code, 'BROWSER_DEPENDENCIES_MISSING');
  assert.match(result.message, /libicu74/);
  assert.match(result.message, /libflite1/);
  assert.match(result.hint, /playwright install-deps webkit/);
  assert.doesNotMatch(JSON.stringify(result), /coreBundle|validateDependencies|╔|\bat /);
  const shared = executionDiagnostic(new Error('MiniBrowser: error while loading shared libraries: libicuuc.so.74: cannot open shared object file'), { browser: 'webkit' });
  assert.equal(shared.code, 'BROWSER_DEPENDENCIES_MISSING');
  assert.match(shared.message, /libicuuc\.so\.74/);
  assert.doesNotMatch(shared.message, /missing: libraries/);
});

test('a missing browser executable names the selected installer target', () => {
  const result = executionDiagnostic(new Error("browserType.launchServer: Executable doesn't exist at /private/browser/firefox"), { browser: 'firefox' });
  assert.equal(result.code, 'BROWSER_EXECUTABLE_MISSING');
  assert.match(result.hint, /playwright install firefox/);
  assert.doesNotMatch(JSON.stringify(result), /private\/browser/);
});

test('fallback retains a bounded cause while omitting launch commands, secrets, and stacks', () => {
  const error = new Error(`browserType.launchServer: Target page, context or browser has been closed
Browser logs:
<launching> /browser --proxy-password=launch-password --user-data-dir=/fixture
[pid=42][err] FATAL: Video backend unavailable (untagged-env-value); proxy user probe-user password proxy-password; endpoint https://user:password@example.test/context?key=query-secret#fragment-secret
Environment: EXAMPLE_TOKEN=environment-secret
    at launch (/fixture/server.js:20:1)
Call log:
  - <launching> /browser --token=launch-token`);
  const result = executionDiagnostic(error, { launchOptions: { env: { CUSTOM_VALUE: 'untagged-env-value', EXAMPLE_TOKEN: 'environment-secret' }, proxy: { username: 'probe-user', password: 'proxy-password' } } });
  assert.match(result.message, /Video backend unavailable/);
  assert.match(result.message, /example\.test\/context/);
  assert.doesNotMatch(JSON.stringify(result), /launch-password|untagged-env-value|probe-user|proxy-password|query-secret|fragment-secret|environment-secret|launch-token|server\.js|<launching>/);
  assert.ok(result.message.length <= 400);
  assert.ok(result.hint.length <= 280);
  const long = executionDiagnostic(new Error(`Unsupported browser option: ${'x'.repeat(5000)}`));
  assert.match(long.message, /Unsupported browser option/);
  assert.ok(long.message.length <= 400);
  const structured = executionDiagnostic(new Error('Proxy rejected credentials: {"password":"unconfigured-password", "api_key":"unconfigured-key"}'));
  assert.match(structured.message, /Proxy rejected/);
  assert.doesNotMatch(structured.message, /unconfigured-password|unconfigured-key/);
});

test('supervisor errors and retained session receipts carry the same sanitized failure', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'pw-diagnostic-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const packagePath = join(directory, 'package'), artifactDir = join(directory, 'evidence'), resourceRoot = join(directory, 'resources');
  await mkdir(packagePath);
  await writeFile(join(packagePath, 'package.json'), JSON.stringify({ name: 'playwright', version: '1.0.0-fixture', main: 'index.cjs' }));
  const message = `${upstreamDependencies}\nEnvironment: EXAMPLE_TOKEN=fixture-environment-secret\nAuthorization: Bearer fixture-auth-secret`;
  await writeFile(join(packagePath, 'index.cjs'), `module.exports={chromium:{launch(){},connect(){},executablePath(){return process.execPath},async launchServer(){throw new Error(${JSON.stringify(message)})}},devices:{}}`);
  let caught;
  await assert.rejects(openSession({ playwrightPath: packagePath, resourceRoot, artifactDir, launchOptions: { env: { EXAMPLE_TOKEN: 'fixture-environment-secret' } }, contextOptions: { httpCredentials: { username: 'fixture-user', password: 'fixture-auth-secret' } } }), error => { caught = error; return error.code === 'BROWSER_DEPENDENCIES_MISSING'; });
  assert.match(caught.message, /libicu74/);
  assert.match(caught.message, /libflite1/);
  const bytes = await readFile(caught.diagnosticPath, 'utf8'), receipt = JSON.parse(bytes);
  assert.deepEqual(receipt.failure, { code: caught.code, message: caught.message, hint: caught.hint });
  assert.equal(receipt.cleanup.status, 'completed');
  assert.doesNotMatch(bytes, /fixture-environment-secret|fixture-auth-secret|fixture-user|coreBundle|Authorization|launchServer|stack/);
  assert.deepEqual(await readdir(resourceRoot), []);
  assert.equal((await readdir(artifactDir)).length, 1);
});
