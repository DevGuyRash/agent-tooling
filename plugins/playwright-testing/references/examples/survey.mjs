#!/usr/bin/env node
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createEvidenceRun, withSession, discover, observeContext, capture, renderGallery } from '../../runtime/index.mjs';

const [input, destination, project = process.cwd()] = process.argv.slice(2);
if (!input || !destination || process.argv.includes('--help')) {
  console.log('Usage: node survey.mjs <url-or-html-file> <new-output-directory> [application-project]');
  process.exit(input === '--help' ? 0 : 2);
}

const url = /^[a-z]:[\\/]/i.test(input) || !URL.canParse(input)
  ? pathToFileURL(resolve(input)).href
  : new URL(input).href;
const outputDir = resolve(destination);
const controller = new AbortController();
const cancel = () => controller.abort(new Error('Survey interrupted.'));
process.once('SIGINT', cancel);
process.once('SIGTERM', cancel);
let run;
try {
  run = await createEvidenceRun({ outputDir, metadata: { question: 'What is visible at this starting state?', target: url } });
  await run.enqueue({ id: 'initial-state', url });
  await withSession({ projectDir: resolve(project), signal: controller.signal }, async ({ page, context, info }) => {
    const diagnostics = observeContext(context);
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded' });
      const observed = await discover(page);
      await run.record({ type: 'discovery', state: { url: page.url() }, observed, environment: info });
      const image = await capture(page, {
        run,
        label: 'Initial state',
        taskId: 'initial-state',
        state: { comparisonKey: 'initial-state', actions: [{ navigate: url }] },
        environment: info,
        diagnostics,
        signal: controller.signal,
      });
      if (image.status === 'complete') await run.complete('initial-state', { observationId: image.id });
      else process.exitCode = 1;
    } finally {
      diagnostics.close();
    }
  });
  await run.finish();
} catch (error) {
  if (run) await run.record({ type: 'execution-error', taskId: 'initial-state', message: error.message }).catch(() => {});
  console.error(`error: ${error.message}`);
  if (error.hint) console.error(`hint: ${error.hint}`);
  process.exitCode = 1;
} finally {
  process.removeListener('SIGINT', cancel);
  process.removeListener('SIGTERM', cancel);
  if (run) {
    try {
      await run.close();
      const gallery = await renderGallery(outputDir);
      console.log(JSON.stringify({ outputDir, index: gallery.indexPath }));
    } catch (error) {
      console.error(`error: evidence finalization failed: ${error.message}`);
      process.exitCode = 1;
    }
  }
}
