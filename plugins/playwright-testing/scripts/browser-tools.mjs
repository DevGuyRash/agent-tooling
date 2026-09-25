#!/usr/bin/env node
import { parseArgs } from 'node:util';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { mkdtemp, rm } from 'node:fs/promises';

const commands = ['doctor', 'isolate-run', 'capture', 'import', 'summary', 'gallery', 'compare', 'recover'];
const help = `Browser Survey and Playwright execution tools

node browser-tools.mjs doctor [--project DIR] [--playwright PATH] [--devices]
node browser-tools.mjs isolate-run [--screen WIDTHxHEIGHT] [--timeout-ms N]
    [--provider MODULE] -- COMMAND ARGUMENTS...
node browser-tools.mjs capture URL_OR_FILE --output DIR [--project DIR]
    [--playwright PATH] [--presentation headless|isolated-headed]
    [--browser ENGINE] [--channel CHANNEL] [--device NAME]
    [--width N --height N] [--scheme light|dark] [--scroll] [--trace]
    [--comparison-key KEY]
node browser-tools.mjs import --input DIR --output DIR
node browser-tools.mjs summary --run DIR [--limit N] [--type TYPE] [--details]
node browser-tools.mjs gallery --run DIR
node browser-tools.mjs compare --left DIR --right DIR --output DIR
node browser-tools.mjs recover --root DIR [--dry-run]

Paths resolve against the invoking directory. Shared resources resolve against
the installed plugin. Headless is the capture default. isolate-run provides
an owned headed environment for an existing command. Setup instructions and
platform capabilities are available through doctor and the shared references.
Output is compact JSON; evidence and complete diagnostics remain in the run.
`;
const string = { type: 'string' };
const boolean = { type: 'boolean' };
const runtimeOptions = { project: string, playwright: string, provider: string };
const definitions = {
  doctor: { ...runtimeOptions, devices: boolean },
  'isolate-run': { ...runtimeOptions, screen: string, 'timeout-ms': string, root: string },
  capture: { ...runtimeOptions, output: string, presentation: string, browser: string, channel: string, device: string, width: string, height: string, scheme: string, scroll: boolean, trace: boolean, label: string, selector: string, 'timeout-ms': string, 'max-frames': string, 'comparison-key': string, offline: boolean },
  import: { input: string, output: string },
  summary: { run: string, limit: string, type: string, details: boolean },
  gallery: { run: string },
  compare: { left: string, right: string, output: string },
  recover: { root: string, 'dry-run': boolean },
};

function required(values, name) {
  if (!values[name]) throw new Error(`--${name} is required. Use --help for the command interface.`);
  return values[name];
}
function integer(value, name) {
  if (value === undefined) return undefined;
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < 1)
    throw new Error(`--${name} needs a positive integer.`);
  return Number(value);
}
function dimensions(value) {
  if (value === undefined) return undefined;
  const match = /^(\d+)x(\d+)$/.exec(value);
  if (!match) throw new Error('--screen needs WIDTHxHEIGHT, for example 1600x1000.');
  return { width: integer(match[1], 'screen'), height: integer(match[2], 'screen') };
}
function targetURL(value) {
  if (/^https?:\/\//i.test(value) || /^file:\/\//i.test(value)) return new URL(value).href;
  if (/^[a-z][a-z0-9+.-]*:/i.test(value) && !/^[a-z]:[\\/]/i.test(value))
    throw new Error('capture accepts an HTTP(S) URL, file URL, or local file path.');
  return pathToFileURL(resolve(value)).href;
}
function runtime(values) {
  return {
    projectDir: values.project ? resolve(values.project) : process.cwd(),
    playwrightPath: values.playwright ? resolve(values.playwright) : undefined,
    provider: values.provider ? resolve(values.provider) : undefined,
  };
}
function print(value) { process.stdout.write(JSON.stringify(value) + '\n'); }

async function captureCommand(api, values, positional, signal) {
  if (positional.length !== 1) throw new Error('capture needs one URL or local file path.');
  const outputDir = resolve(required(values, 'output'));
  const url = targetURL(positional[0]);
  const presentation = values.presentation ?? 'headless';
  if (!['headless', 'isolated-headed'].includes(presentation))
    throw new Error('--presentation must be headless or isolated-headed.');
  if (values.scheme && !['light', 'dark'].includes(values.scheme))
    throw new Error('--scheme must be light or dark.');
  const width = integer(values.width, 'width'), height = integer(values.height, 'height');
  if ((width === undefined) !== (height === undefined)) throw new Error('Supply --width and --height together.');
  const timeout = integer(values['timeout-ms'], 'timeout-ms') ?? 30000;
  const run = await api.createEvidenceRun({ outputDir, metadata: { purpose: 'browser capture', source: url } });
  let session, observer, traceDir, observation, navigationError, failure, gallery;
  let traceStarted = false, traceStored = false;
  const problems = [];
  async function problem(type, error) {
    problems.push({ type, message: error.message });
    try { await run.record({ type, message: error.message }); }
    catch (recordError) { problems.push({ type: 'evidence-write-error', message: recordError.message }); }
  }
  try {
    session = await api.openSession({
      ...runtime(values), presentation, browser: values.browser,
      channel: values.channel, device: values.device, viewport: width ? { width, height } : undefined,
      contextOptions: { ...(values.scheme ? { colorScheme: values.scheme } : {}), ...(values.offline ? { offline: true } : {}) },
      signal,
    });
    await run.record({ type: 'session', info: session.info });
    observer = api.observeContext(session.context, { limit: 100 });
    if (values.trace) {
      traceDir = await mkdtemp(join(outputDir, '.trace-'));
      await session.context.tracing.start({ screenshots: true, snapshots: true, sources: false });
      traceStarted = true;
    }
    try { await session.page.goto(url, { waitUntil: 'domcontentloaded', timeout }); }
    catch (error) {
      navigationError = error.message;
      await run.record({ type: 'navigation-error', url, message: navigationError });
    }
    const comparisonKey = values['comparison-key'] ?? {
      source: url, target: values.selector ?? null, scroll: !!values.scroll,
      viewport: session.info.requested?.viewport, screen: session.info.requested?.screen,
      browser: session.info.browser, channel: session.info.channel, device: session.info.device,
      colorPreference: values.scheme ?? 'system', offline: !!values.offline,
    };
    observation = await api.capture(session.page, {
      run, label: values.label ?? url, state: { requestedURL: url, comparisonKey }, environment: session.info,
      target: values.selector, timeout, diagnostics: observer,
      scroll: values.scroll ? { maxFrames: integer(values['max-frames'], 'max-frames') ?? 40 } : undefined,
      readiness: { timeout, signal },
    });
  } catch (error) {
    failure = error;
    await problem('capture-error', error);
  } finally {
    if (traceStarted) {
      try {
        const trace = join(traceDir, 'trace.zip');
        await session.context.tracing.stop({ path: trace });
        const artifact = await run.storeArtifact(trace, { extension: 'zip', mime: 'application/zip' });
        await run.record({ type: 'trace', captureId: observation?.id, artifacts: [artifact] });
        traceStored = true;
      } catch (error) { await problem('trace-error', error); }
    }
    observer?.close();
    if (session) {
      try { await session.close(); }
      catch (error) { await problem('cleanup-error', error); }
    }
    if (traceDir && traceStored) await rm(traceDir, { recursive: true, force: true });
    try { await run.finish(); }
    catch (error) { await problem('evidence-finish-error', error); }
    finally { await run.close(); }
    try { gallery = await api.renderGallery(outputDir); }
    catch (error) { problems.push({ type: 'gallery-error', message: error.message }); }
  }
  print({ outputDir, gallery: gallery?.indexPath, observationId: observation?.id, status: observation?.status, navigationError, problems, ...(traceDir && !traceStored ? { retainedTraceDirectory: traceDir } : {}) });
  if (failure) throw failure;
  if (navigationError || problems.length || observation?.status === 'partial' || observation?.status === 'failed' || observation?.status === 'cancelled') process.exitCode = 1;
}

async function main(args) {
  const command = args.shift();
  if (!command || command === '--help' || command === '-h') { process.stdout.write(help); return; }
  if (!commands.includes(command)) throw new Error(`unknown command "${command}". Valid commands: ${commands.join(', ')}.`);
  const separator = args.indexOf('--');
  const child = separator === -1 ? [] : args.slice(separator + 1);
  const own = separator === -1 ? args : args.slice(0, separator);
  const { values, positionals } = parseArgs({ args: own, allowPositionals: true, options: { ...definitions[command], help: { type: 'boolean', short: 'h' } } });
  if (values.help) { process.stdout.write(help); return; }
  if (command !== 'capture' && positionals.length) throw new Error(`unexpected positional argument for ${command}.`);
  if (command !== 'isolate-run' && child.length) throw new Error('-- COMMAND is supported by isolate-run.');
  const api = await import('../runtime/index.mjs');
  const controller = new AbortController();
  let interrupted;
  const stop = name => { interrupted = name; controller.abort(new Error(`Interrupted by ${name}.`)); };
  const onInt = () => stop('SIGINT'), onTerm = () => stop('SIGTERM');
  process.once('SIGINT', onInt); process.once('SIGTERM', onTerm);
  try {
    if (command === 'doctor') print(await api.inspectCapabilities({ ...runtime(values), devices: !!values.devices }));
    else if (command === 'isolate-run') {
      if (!child.length) throw new Error('isolate-run needs -- COMMAND ARGUMENTS...');
      const result = await api.runIsolated(child[0], child.slice(1), {
        ...runtime(values), cwd: process.cwd(), screen: dimensions(values.screen),
        timeout: integer(values['timeout-ms'], 'timeout-ms'),
        resourceRoot: values.root ? resolve(values.root) : undefined,
        signal: controller.signal, stdio: 'inherit',
      });
      process.exitCode = result.exitCode ?? (result.signal ? 1 : 0);
    } else if (command === 'capture') await captureCommand(api, values, positionals, controller.signal);
    else if (command === 'import') {
      const result = await api.importCaptureCollection(resolve(required(values, 'input')), { outputDir: resolve(required(values, 'output')), signal: controller.signal });
      const gallery = await api.renderGallery(result.outputDir);
      print({ ...result, gallery: gallery.indexPath });
    }
    else if (command === 'summary') print(await api.readEvidenceRun(resolve(required(values, 'run')), { limit: integer(values.limit, 'limit') ?? 25, type: values.type, includeRecords: !!values.details }));
    else if (command === 'gallery') print(await api.renderGallery(resolve(required(values, 'run'))));
    else if (command === 'compare') {
      const result = await api.compareRuns(resolve(required(values, 'left')), resolve(required(values, 'right')), { outputDir: resolve(required(values, 'output')) });
      const gallery = await api.renderGallery(result.outputDir);
      print({ outputDir: result.outputDir, summary: result.summary, comparison: join(result.outputDir, 'comparison.json'), gallery: gallery.indexPath });
    }
    else if (command === 'recover') print(await api.recoverOwnedResources(resolve(required(values, 'root')), { dryRun: !!values['dry-run'] }));
  } finally {
    process.removeListener('SIGINT', onInt); process.removeListener('SIGTERM', onTerm);
    if (interrupted) process.exitCode = interrupted === 'SIGINT' ? 130 : 143;
  }
}

main(process.argv.slice(2)).catch(error => {
  process.stderr.write(`error: ${error.message}\n`);
  if (error.hint) process.stderr.write(`hint: ${error.hint}\n`);
  if (!process.exitCode) process.exitCode = 1;
});
