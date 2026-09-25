import { randomUUID } from 'node:crypto';
import { copyFile, lstat, mkdir, open, readFile, readdir, rename, rm, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { acquireEvidenceLock, iterateEvidenceEvents, readEvidenceRun, verifyEvidenceArtifact } from './evidence.mjs';

const assets = fileURLToPath(new URL('./assets/', import.meta.url));
const html = value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
const scriptJson = value => `JSON.parse(${JSON.stringify(JSON.stringify(value)).replaceAll('<', '\\u003c').replaceAll('\u2028', '\\u2028').replaceAll('\u2029', '\\u2029')})`;
const searchable = value => value == null ? '' : typeof value === 'object' ? Object.values(value).map(searchable).join('\n') : String(value);
const exists = async file => stat(file).then(() => true, error => { if (error.code === 'ENOENT') return false; throw error; });
const layout = (title, content, links = '') => `<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'"><title>${html(title)}</title>${links}</head><body>${content}</body></html>\n`;

async function safeImage(root, ref, cache) {
  if (!ref || typeof ref !== 'object' || !/^[a-f0-9]{64}$/.test(ref.sha256 || '') || ref.path !== `blobs/${ref.sha256.slice(0, 2)}/${ref.sha256}`) throw new Error('Invalid gallery artifact reference; expected a content-addressed blob.');
  await verifyEvidenceArtifact(root, ref, cache);
  return { ...ref, displayable: /^image\/(png|jpeg|webp|gif|avif|svg\+xml)$/.test(ref.mime || '') };
}

/** Render a portable local-file gallery. The generated UI treats all evidence text as data. */
export async function renderGallery(runDir, { title = 'Browser evidence', includeProgress = false } = {}) {
  runDir = path.resolve(runDir);
  const evidence = await readEvidenceRun(runDir, { includeRecords: false });
  const finalIds = new Set();
  for await (const event of iterateEvidenceEvents(runDir)) if (event.event === 'observation' && event.observation.type === 'capture') finalIds.add(event.observation.id);
  const release = await acquireEvidenceLock(runDir, '.gallery-lock');
  const staging = path.join(runDir, `.gallery-${randomUUID()}`);
  const destination = path.join(runDir, 'gallery');
  const backup = path.join(runDir, `.gallery-previous-${randomUUID()}`);
  let moved = false;
  try {
    const abandoned = [];
    for (const name of await readdir(runDir)) {
      if (!/^\.gallery-(?:previous-)?[a-f0-9-]{36}$/.test(name)) continue;
      const directory = path.join(runDir, name);
      if ((await lstat(directory)).isSymbolicLink()) continue;
      const owner = JSON.parse(await readFile(path.join(directory, 'owner.json'), 'utf8').catch(() => '{}'));
      if (owner.runId === evidence.run.id) abandoned.push({ directory, previous: name.startsWith('.gallery-previous-'), at: owner.generatedAt || '' });
    }
    if (!await exists(destination)) {
      const prior = abandoned.filter(item => item.previous).sort((a, b) => b.at.localeCompare(a.at))[0];
      if (prior) { await rename(prior.directory, destination); abandoned.splice(abandoned.indexOf(prior), 1); }
    }
    for (const item of abandoned) await rm(item.directory, { recursive: true, force: true });
    if (await exists(destination)) {
      if ((await lstat(destination)).isSymbolicLink()) throw new Error('Gallery output must be a real owned directory.');
      const owner = JSON.parse(await readFile(path.join(destination, 'owner.json'), 'utf8').catch(() => '{}'));
      if (owner.runId !== evidence.run.id) throw new Error('Gallery output contains unrelated files; preserve or move them before generation.');
    }
    await mkdir(path.join(staging, 'records'), { recursive: true, mode: 0o700 });
    const ownership = await open(path.join(staging, 'owner.json'), 'wx', 0o600);
    try { await ownership.writeFile(JSON.stringify({ runId: evidence.run.id, generatedAt: new Date().toISOString() })); } finally { await ownership.close(); }
    for (const name of ['gallery.css', 'gallery-app.js']) await copyFile(path.join(assets, name), path.join(staging, name));
    const data = await open(path.join(staging, 'gallery-data.js'), 'wx', 0o600);
    let observations = 0, images = 0, hiddenProgress = 0;
    const imageCache = new Map(), transitions = [];
    try {
      await data.writeFile(`globalThis.__evidence={run:${scriptJson(evidence.run)},summary:${scriptJson(evidence.summary)},pendingTasks:${scriptJson(evidence.pendingTasks || [])},records:[\n`);
      for await (const event of iterateEvidenceEvents(runDir)) {
        if (event.event !== 'observation') continue;
        const record = event.observation;
        if (!includeProgress && record.type === 'capture-progress' && finalIds.has(record.captureId)) { hiddenProgress += 1; continue; }
        const index = observations++, name = `${String(index + 1).padStart(6, '0')}.html`;
        const refs = [];
        for (const ref of Array.isArray(record.images) ? record.images : []) refs.push(await safeImage(runDir, ref, imageCache));
        images += refs.length;
        const label = record.label || record.id;
        const source = JSON.stringify(record, null, 2);
        const detail = layout(label, `<main class="record-page"><a href="../index.html">← Evidence gallery</a><header><p class="eyebrow">${html(record.type || 'Observation')}</p><h1>${html(label)}</h1><p>${html(record.id)}</p></header>${refs.length ? `<input id="original-size" class="original-size" type="checkbox"><label for="original-size">Show images at original pixel size</label><section class="detail-images" aria-label="Original images">${refs.map((ref, i) => `<figure>${ref.displayable ? `<img src="../../${html(ref.path)}" alt="${html(label)} — ${html(ref.side || `image ${i + 1}`)}" loading="lazy">` : ''}<figcaption>${html(ref.side || `Image ${i + 1}`)} · ${html(ref.size)} bytes · <a href="../../${html(ref.path)}" download="${html(ref.sha256)}.${html(ref.extension || 'bin')}">Download original</a></figcaption></figure>`).join('')}</section>` : ''}<h2>Reproduction and original context</h2><pre tabindex="0">${html(source)}</pre></main>`, '<link rel="stylesheet" href="../gallery.css">');
        const handle = await open(path.join(staging, 'records', name), 'wx', 0o600);
        try { await handle.writeFile(detail); } finally { await handle.close(); }
        const state = record.state || {};
        const descriptor = { id: record.id, label, type: record.type || 'observation', status: record.status || '', state, images: refs, detail: `records/${name}`, at: record.recordedAt || event.at, search: searchable({ label, id: record.id, state, status: record.status, diagnostics: record.diagnostics, readiness: record.readiness, context: record.type === 'comparison' ? record.context?.status : undefined }) };
        if (index) await data.writeFile(',\n');
        await data.writeFile(scriptJson(descriptor));
        if (record.type === 'transition') transitions.push({ id: record.id, from: record.from, to: record.to, action: record.action || record.label || '', detail: `records/${name}` });
      }
      await data.writeFile(`],transitions:${scriptJson(transitions)}};\n`);
      await data.sync();
    } finally { await data.close(); }
    const content = `<a class="skip" href="#results">Skip to evidence</a><header class="masthead"><div><p class="eyebrow">Browser survey</p><h1>${html(title)}</h1><p id="summary" class="muted"></p></div><button id="appearance" type="button" aria-label="Change appearance">Appearance: system</button></header><main><section class="toolbar" aria-label="Find evidence"><div class="filter search"><label for="search">Search</label><input id="search" type="search" placeholder="Page, state, observation, or diagnostic"></div><div class="filter"><label for="type">Type</label><select id="type"><option value="">All types</option></select></div><div class="filter"><label for="viewport">Viewport</label><select id="viewport"><option value="">All sizes</option></select></div><div class="filter"><label for="scheme">Appearance</label><select id="scheme"><option value="">All appearances</option></select></div><div class="filter"><label for="group">Group</label><select id="group"><option value="none">Observation order</option><option value="page">Page</option><option value="viewport">Viewport</option><option value="type">Type</option></select></div></section><details id="pending" hidden><summary id="pending-title">Pending work</summary><pre id="pending-context" tabindex="0"></pre></details><details id="map" hidden><summary>Observed transitions</summary><p class="muted">Arrows represent recorded actions between states.</p><div id="transition-map"></div><ul id="transition-list"></ul></details><div class="results-bar"><p id="result-count" role="status" aria-live="polite"></p><div class="pagination"><button id="previous" type="button">Previous</button><span id="page-number"></span><button id="next" type="button">Next</button></div></div><section id="results" tabindex="-1" aria-label="Evidence images"></section><p id="empty" hidden>No evidence matches these filters.</p><footer><a href="../run.json">Run metadata</a><a href="../observations.ndjson">All original records</a><span>Exact originals remain available for each observation.</span></footer></main>`;
    await copyFile(path.join(assets, 'gallery.css'), path.join(staging, 'gallery.css'));
    const index = await open(path.join(staging, 'index.html'), 'wx', 0o600);
    try { await index.writeFile(layout(title, content, '<link rel="stylesheet" href="gallery.css"><script src="gallery-data.js" defer></script><script src="gallery-app.js" defer></script>')); } finally { await index.close(); }
    if (await exists(destination)) { await rename(destination, backup); moved = true; }
    try { await rename(staging, destination); } catch (error) { if (moved) await rename(backup, destination); moved = false; throw error; }
    if (moved) await rm(backup, { recursive: true, force: true });
    return { outputDir: runDir, indexPath: path.join(destination, 'index.html'), observations, images, hiddenProgress, pendingTasks: evidence.summary.pendingTasks };
  } finally { await rm(staging, { recursive: true, force: true }); await release(); }
}
