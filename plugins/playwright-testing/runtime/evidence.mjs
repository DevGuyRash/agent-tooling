import { createHash, randomUUID } from 'node:crypto';
import { constants, createReadStream, createWriteStream } from 'node:fs';
import { access, mkdir, open, readFile, readdir, realpath, rename, rm, lstat, stat, link, truncate } from 'node:fs/promises';
import { hostname } from 'node:os';
import path from 'node:path';
import { Transform } from 'node:stream';
import { pipeline } from 'node:stream/promises';

const FORMAT = 'playwright-evidence';
const VERSION = 1;
const JOURNAL = 'observations.ndjson';
const LOCK = '.writer-lock';
const HEX = /^[a-f0-9]{64}$/;
const fail = (message, hint) => Object.assign(new Error(`${message}${hint ? `\nhint: ${hint}` : ''}`), { code: 'EVIDENCE_ERROR' });
const json = value => {
  try {
    const encoded = JSON.stringify(value, (_key, entry) => { if (['function', 'symbol', 'bigint'].includes(typeof entry) || typeof entry === 'number' && !Number.isFinite(entry)) throw new Error('unsupported JSON value'); return entry; });
    if (encoded === undefined) throw new Error('undefined');
    return encoded;
  } catch { throw fail('Evidence must be JSON-serializable.', 'Replace functions, circular references, or BigInt values with their observable context.'); }
};
const clone = value => JSON.parse(json(value));
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const now = () => new Date().toISOString();
const hashBytes = bytes => createHash('sha256').update(bytes).digest('hex');
const exists = async file => access(file).then(() => true, error => { if (error.code === 'ENOENT') return false; throw error; });
const sameFile = (a, b) => a.dev === b.dev && a.ino === b.ino && a.size === b.size && a.mtimeMs === b.mtimeMs && a.ctimeMs === b.ctimeMs;

async function syncDirectory(directory) {
  const handle = await open(directory, 'r').catch(() => null);
  if (handle) { try { await handle.sync(); } catch (error) { if (!['EINVAL', 'EPERM', 'EISDIR', 'EBADF'].includes(error.code)) throw error; } finally { await handle.close(); } }
}

async function atomicJson(file, value) {
  const temporary = `${file}.${randomUUID()}.tmp`;
  const handle = await open(temporary, 'wx', 0o600);
  try {
    await handle.writeFile(`${json(value)}\n`);
    await handle.sync();
    await handle.close();
    await rename(temporary, file);
    await syncDirectory(path.dirname(file));
  } finally { await handle.close().catch(() => {}); await rm(temporary, { force: true }); }
}

async function ownedDirectory(root, relative) {
  let directory = root;
  for (const segment of relative.split('/')) {
    directory = path.join(directory, segment);
    await mkdir(directory, { mode: 0o700 }).catch(error => { if (error.code !== 'EEXIST') throw error; });
    const info = await lstat(directory);
    if (!info.isDirectory() || info.isSymbolicLink()) throw fail(`Evidence subdirectory must be owned and real: ${relative}`);
  }
  return directory;
}
async function regularMutableFile(file) {
  const info = await lstat(file).catch(error => { if (error.code === 'ENOENT') return null; throw error; });
  if (info && (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1)) throw fail('Mutable evidence files must be regular files with one owner.');
}

async function readMetadata(runDir) {
  const file = path.join(runDir, 'run.json');
  let metadata;
  try { metadata = JSON.parse(await readFile(file, 'utf8')); } catch (error) { throw fail(`Cannot read evidence run: ${file}`, error.code === 'ENOENT' ? 'Choose a directory containing run.json.' : 'Retain the file and inspect its JSON before resuming.'); }
  if (metadata.format !== FORMAT || metadata.version !== VERSION || typeof metadata.id !== 'string') throw fail('Unsupported evidence format or version.', `Expected ${FORMAT} version ${VERSION}.`);
  return metadata;
}

/** Resolve a prospective output through existing filesystem ancestors before creating it. */
async function separateOutput(outputDir, sources, label) {
  if (typeof outputDir !== 'string' || !outputDir) throw fail(`${label} outputDir is required.`);
  const requested = path.resolve(outputDir), missing = [];
  let ancestor = requested, canonical;
  while (true) {
    try { canonical = await realpath(ancestor); break; }
    catch (error) {
      if (error.code !== 'ENOENT') throw fail(`Cannot resolve ${label.toLowerCase()} output ancestry.`, 'Choose an output beneath an accessible directory.');
      const parent = path.dirname(ancestor);
      if (parent === ancestor) throw fail(`Cannot resolve ${label.toLowerCase()} output ancestry.`);
      missing.unshift(path.basename(ancestor)); ancestor = parent;
    }
  }
  const destination = path.join(canonical, ...missing);
  const sourceRoots = await Promise.all(sources.map(source => realpath(source)));
  const isWithin = (source, candidate) => { const relative = path.relative(source, candidate); return relative === '' || relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative); };
  const refusal = () => fail(`${label} output must be a separate directory outside ${sourceRoots.length === 1 ? 'the source collection' : 'both source runs'}.`);
  if (sourceRoots.some(source => isWithin(source, destination))) throw refusal();
  // Directory identity also detects aliases which retain a distinct path (for example a mounted source root).
  const identities = new Set(await Promise.all(sourceRoots.map(async source => { const info = await stat(source, { bigint: true }); return `${info.dev}:${info.ino}`; })));
  for (let current = canonical; ; current = path.dirname(current)) {
    const info = await stat(current, { bigint: true });
    if (identities.has(`${info.dev}:${info.ino}`)) throw refusal();
    if (path.dirname(current) === current) break;
  }
  if (!missing.length && (await lstat(requested)).isSymbolicLink()) throw fail(`${label} output must be an owned directory, not a symbolic link.`);
  return destination;
}

/** Resolve only a relative regular file contained by its input collection. */
export async function resolveEvidenceFile(root, relative) {
  if (typeof relative !== 'string' || !relative || relative.includes('\0') || relative.includes('\\') || path.posix.isAbsolute(relative) || /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(relative) || relative.split('/').some(part => part === '..')) throw fail('Evidence path must be a contained relative file.', 'Use forward slashes and paths inside the collection.');
  const base = await realpath(root);
  const requested = path.resolve(base, relative);
  const actual = await realpath(requested);
  const info = await lstat(requested);
  if (actual === base || !actual.startsWith(`${base}${path.sep}`) || !info.isFile() || info.isSymbolicLink()) throw fail(`Evidence path is not a contained regular file: ${relative}`);
  return actual;
}

/** Stream committed journal lines; an incomplete final append is reported without accepting it. */
export async function* iterateEvidenceEvents(runDir, { recovery = {} } = {}) {
  const file = path.join(runDir, JOURNAL);
  let pieces = [], pendingLength = 0, committedBytes = 0, line = 0;
  try {
    for await (const chunk of createReadStream(file)) {
      let start = 0, end;
      while ((end = chunk.indexOf(10, start)) !== -1) {
        const segment = chunk.subarray(start, end);
        const bytes = pieces.length ? Buffer.concat([...pieces, segment], pendingLength + segment.length) : segment;
        pieces = []; pendingLength = 0;
        line += 1;
        let event;
        try { event = JSON.parse(bytes.toString('utf8')); } catch { throw fail(`Evidence journal contains an invalid committed record at line ${line}.`, 'Preserve the journal and repair the damaged record before resuming.'); }
        if (!object(event) || event.version !== VERSION || !['observation', 'enqueue', 'complete', 'finish', 'recovery'].includes(event.event)) throw fail(`Unknown evidence journal event at line ${line}.`);
        committedBytes += bytes.length + 1;
        start = end + 1;
        yield event;
      }
      if (start < chunk.length) { const remaining = chunk.subarray(start); pieces.push(remaining); pendingLength += remaining.length; }
    }
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  recovery.committedBytes = committedBytes;
  recovery.trailingBytes = pieces.length ? Buffer.concat(pieces, pendingLength) : Buffer.alloc(0);
}

async function processJournal(runDir, onObservation = () => {}) {
  const ids = new Set(), tasks = new Map(), recovery = {};
  let finishedAt = null;
  for await (const entry of iterateEvidenceEvents(runDir, { recovery })) {
    if (entry.event !== 'finish') finishedAt = null;
    if (entry.event === 'observation') {
      if (!object(entry.observation) || typeof entry.observation.id !== 'string' || ids.has(entry.observation.id)) throw fail('Evidence journal contains a missing or repeated observation identity.');
      ids.add(entry.observation.id);
      await onObservation(entry.observation);
    } else if (entry.event === 'enqueue') {
      if (!object(entry.task) || typeof entry.task.id !== 'string' || tasks.has(entry.task.id)) throw fail('Evidence journal contains a missing or repeated task identity.');
      tasks.set(entry.task.id, { task: entry.task, completed: false });
    } else if (entry.event === 'complete') {
      const task = tasks.get(entry.taskId);
      if (!task || task.completed) throw fail('Evidence journal completes an absent or already completed task.');
      task.completed = true; task.result = entry.result; task.completedAt = entry.at;
    } else if (entry.event === 'finish') finishedAt = entry.at;
  }
  return { ids, tasks, recovery, finishedAt };
}

export async function acquireEvidenceLock(runDir, name = LOCK) {
  if (!/^\.[a-z-]+$/.test(name)) throw fail('Evidence lock name is invalid.');
  const lock = path.join(runDir, name);
  const owner = { token: randomUUID(), pid: process.pid, host: hostname(), createdAt: now() };
  for (let attempt = 0; attempt < 2; attempt++) {
    try { await mkdir(lock, { mode: 0o700 }); }
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      let prior;
      try { prior = JSON.parse(await readFile(path.join(lock, 'owner.json'), 'utf8')); } catch { throw fail('Evidence run has an incomplete ownership lock.', `Confirm the owning writer has stopped before removing ${name}.`); }
      let dead = false;
      if (prior.host === hostname() && Number.isSafeInteger(prior.pid) && prior.pid > 0) {
        try { process.kill(prior.pid, 0); } catch (error) { dead = error.code === 'ESRCH'; }
      }
      if (!dead) throw fail('Evidence run is owned by another writer.', 'Close that writer or choose another output directory.');
      const recoveryLock = `${lock}-recovery`;
      try { await mkdir(recoveryLock, { mode: 0o700 }); } catch (error) { if (error.code === 'EEXIST') throw fail('Another writer is recovering the evidence lock.', 'Retry after recovery; retain an abandoned recovery lock for inspection.'); throw error; }
      try {
        const current = JSON.parse(await readFile(path.join(lock, 'owner.json'), 'utf8'));
        if (current.token !== prior.token) throw fail('Evidence owner changed during recovery.', 'Retry opening the run.');
        const stale = `${lock}.stale-${randomUUID()}`;
        await rename(lock, stale);
        // Only a confirmed dead local owner is reclaimed. PID reuse remains a conservative conflict.
        await rm(stale, { recursive: true, force: true });
      } finally { await rm(recoveryLock, { recursive: true, force: true }); }
      continue;
    }
    try { await atomicJson(path.join(lock, 'owner.json'), owner); } catch (error) { await rm(lock, { recursive: true, force: true }); throw error; }
    return async () => {
      let current;
      try { current = JSON.parse(await readFile(path.join(lock, 'owner.json'), 'utf8')); } catch { return; }
      if (current.token === owner.token) await rm(lock, { recursive: true, force: true });
    };
  }
  throw fail('Evidence run ownership changed during recovery.', 'Retry opening the run.');
}

function mimeFor(extension) {
  return ({ png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif', avif: 'image/avif', svg: 'image/svg+xml', json: 'application/json', zip: 'application/zip', webm: 'video/webm', mp4: 'video/mp4', txt: 'text/plain', html: 'text/html', md: 'text/markdown' })[extension] || 'application/octet-stream';
}
function artifactOptions({ extension = 'bin', mime } = {}) {
  extension = extension.replace(/^\./, '').toLowerCase();
  if (!/^[a-z0-9]{1,16}$/.test(extension)) throw fail('Artifact extension must contain 1–16 letters or digits.');
  mime ||= mimeFor(extension);
  if (typeof mime !== 'string' || !/^[\w.+-]+\/[\w.+-]+$/.test(mime)) throw fail('Artifact MIME type is invalid.');
  return { extension, mime };
}
async function hashFile(file) {
  const hash = createHash('sha256'); let size = 0;
  for await (const chunk of createReadStream(file)) { hash.update(chunk); size += chunk.length; }
  return { sha256: hash.digest('hex'), size };
}

/** Verify bytes before presenting their recorded identity as evidence. */
export async function verifyEvidenceArtifact(root, ref, cache = new Map()) {
  if (!object(ref) || !HEX.test(ref.sha256 || '') || typeof ref.path !== 'string' || !Number.isSafeInteger(ref.size) || ref.size < 0) throw fail('Artifact reference needs a SHA-256, contained path, and byte size.');
  const key = `${path.resolve(root)}\0${ref.path}\0${ref.sha256}\0${ref.size}`;
  if (cache.has(key)) return cache.get(key);
  const file = await resolveEvidenceFile(root, ref.path);
  const observed = await hashFile(file);
  if (observed.sha256 !== ref.sha256 || observed.size !== ref.size) throw fail(`Artifact bytes differ from their recorded identity: ${ref.path}`);
  cache.set(key, file);
  return file;
}

/** Create one owned append-only evidence writer. close() leaves unfinished tasks resumable. */
export async function createEvidenceRun({ outputDir, resume = false, metadata = {}, durability } = {}) {
  if (typeof outputDir !== 'string' || !outputDir) throw fail('outputDir is required.');
  if (!object(metadata)) throw fail('Evidence metadata must be an object.');
  if (durability !== undefined && !['process', 'disk'].includes(durability)) throw fail('durability must be process or disk.');
  const runDir = path.resolve(outputDir);
  await mkdir(runDir, { recursive: true, mode: 0o700 });
  if ((await lstat(runDir)).isSymbolicLink()) throw fail('Evidence output must be an owned directory, not a symbolic link.');
  const release = await acquireEvidenceLock(runDir);
  let file, loaded;
  try {
    const present = await exists(path.join(runDir, 'run.json'));
    if (present && !resume) throw fail('Evidence output already contains a run.', 'Pass resume:true or choose a new output directory.');
    if (present) {
      loaded = await readMetadata(runDir);
      if (durability && loaded.durability && durability !== loaded.durability) throw fail('Resume durability differs from the original run.', 'Retain the original mode or choose a new output directory.');
      if (Object.keys(metadata).length && canonicalEvidenceKey(loaded.metadata) !== canonicalEvidenceKey(clone(metadata))) throw fail('Resume metadata differs from the original run.', 'Omit metadata to retain the original, or create another run.');
    } else {
      const unrelated = (await readdir(runDir)).filter(name => name !== LOCK);
      if (unrelated.length) throw fail('Evidence output contains unrelated files.', 'Choose a new or empty directory.');
      loaded = { format: FORMAT, version: VERSION, id: randomUUID(), createdAt: now(), durability: durability || 'process', metadata: clone(metadata) };
      await atomicJson(path.join(runDir, 'run.json'), loaded);
    }
    const diskDurability = (loaded.durability || 'process') === 'disk';
    await ownedDirectory(runDir, '.staging');
    await regularMutableFile(path.join(runDir, JOURNAL));
    const state = await processJournal(runDir);
    let recovered;
    if (state.recovery.trailingBytes?.length) {
      const rel = `recovery/trailing-${randomUUID()}.bin`;
      await ownedDirectory(runDir, 'recovery');
      const recoveredFile = await open(path.join(runDir, rel), 'wx', 0o600);
      try { await recoveredFile.writeFile(state.recovery.trailingBytes); await recoveredFile.sync(); } finally { await recoveredFile.close(); }
      await truncate(path.join(runDir, JOURNAL), state.recovery.committedBytes);
      recovered = { event: 'recovery', version: VERSION, at: now(), path: rel, bytes: state.recovery.trailingBytes.length };
    }
    file = await open(path.join(runDir, JOURNAL), 'a', 0o600);
    // Files in this private staging owner are incomplete, never published blobs.
    for (const entry of await readdir(path.join(runDir, '.staging'))) await rm(path.join(runDir, '.staging', entry), { force: true });
    let closed = false, queue = Promise.resolve();
    const serialize = fn => {
      if (closed) return Promise.reject(fail('Evidence run is closed.', 'Open it with resume:true to append.'));
      const work = queue.then(fn);
      queue = work.catch(() => {});
      return work;
    };
    let poisoned = false;
    const append = async event => {
      if (poisoned) throw fail('Evidence journal needs recovery after a failed write.', 'Close this writer and reopen with resume:true.');
      const line = `${json({ version: VERSION, at: now(), ...event })}\n`;
      try { await file.appendFile(line); if (diskDurability) await file.sync(); } catch (error) { poisoned = true; throw error; }
    };
    if (recovered) await append(recovered);
    const publish = async (temporary, sha256, size, options) => {
      const rel = `blobs/${sha256.slice(0, 2)}/${sha256}`;
      const destination = path.join(runDir, rel);
      await ownedDirectory(runDir, `blobs/${sha256.slice(0, 2)}`);
      try { await link(temporary, destination); }
      catch (error) {
        if (error.code !== 'EEXIST') throw error;
        const check = await hashFile(await resolveEvidenceFile(runDir, rel));
        if (check.sha256 !== sha256 || check.size !== size) throw fail(`Stored artifact is damaged: ${rel}`, 'Preserve the damaged run and restore the exact original artifact before resuming.');
      }
      if (diskDurability) await syncDirectory(path.dirname(destination));
      return { sha256, path: rel, size, mime: options.mime, extension: options.extension };
    };
    const run = {
      outputDir: runDir, id: loaded.id, durability: loaded.durability || 'process', metadata: clone(loaded.metadata),
      record(observation) {
        if (!object(observation)) return Promise.reject(fail('Observation must be an object.'));
        const saved = clone(observation);
        saved.id ??= randomUUID();
        if (typeof saved.id !== 'string' || !saved.id) return Promise.reject(fail('Observation id must be a non-empty string.'));
        saved.recordedAt ??= now();
        return serialize(async () => {
          if (state.ids.has(saved.id)) throw fail(`Observation id already exists: ${saved.id}`, 'Use a distinct identity; existing observations remain immutable.');
          await append({ event: 'observation', observation: saved });
          state.ids.add(saved.id);
          return clone(saved);
        });
      },
      storeBlob(bytes, options) {
        if (!(bytes instanceof Uint8Array) && !(bytes instanceof ArrayBuffer)) return Promise.reject(fail('Blob bytes must be a Uint8Array or ArrayBuffer.'));
        const owned = Buffer.from(bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : bytes);
        const settings = artifactOptions(options);
        return serialize(async () => {
          const temporary = path.join(runDir, '.staging', randomUUID());
          const handle = await open(temporary, 'wx', 0o600);
          try { await handle.writeFile(owned); if (diskDurability) await handle.sync(); await handle.close(); return await publish(temporary, hashBytes(owned), owned.length, settings); }
          finally { await handle.close().catch(() => {}); await rm(temporary, { force: true }); }
        });
      },
      storeArtifact(filePath, options = {}) {
        const source = path.resolve(filePath);
        const settings = artifactOptions({ extension: path.extname(source).slice(1) || 'bin', ...options });
        return serialize(async () => {
          if (!(await lstat(source)).isFile()) throw fail('Artifact source must be a regular file.');
          const input = await open(source, constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
          const before = await input.stat();
          if (!before.isFile()) { await input.close(); throw fail('Artifact source must be a regular file.'); }
          const temporary = path.join(runDir, '.staging', randomUUID());
          const hash = createHash('sha256'); let size = 0;
          try {
            await pipeline(input.createReadStream({ autoClose: false }), new Transform({ transform(chunk, _encoding, callback) { hash.update(chunk); size += chunk.length; callback(null, chunk); } }), createWriteStream(temporary, { flags: 'wx', mode: 0o600 }));
            const after = await input.stat();
            if (!sameFile(before, after)) throw fail('Artifact changed while being copied.', 'Retry after its producer has finished writing.');
            if (diskDurability) {
              const destination = await open(temporary, 'r');
              try { await destination.sync(); } finally { await destination.close(); }
            }
            return await publish(temporary, hash.digest('hex'), size, settings);
          } finally { await input.close(); await rm(temporary, { force: true }); }
        });
      },
      enqueue(task) {
        if (!object(task) || typeof task.id !== 'string' || !task.id) return Promise.reject(fail('Pending tasks require a non-empty string id.'));
        const saved = clone(task);
        return serialize(async () => {
          const prior = state.tasks.get(saved.id);
          if (prior) {
            if (canonicalEvidenceKey(prior.task) === canonicalEvidenceKey(saved)) return clone(prior.task);
            throw fail(`Task identity already has different context: ${saved.id}`, 'Use a new identity for a different task.');
          }
          await append({ event: 'enqueue', task: saved }); state.tasks.set(saved.id, { task: saved, completed: false }); return clone(saved);
        });
      },
      complete(taskId, result = null) {
        const saved = clone(result);
        return serialize(async () => {
          const task = state.tasks.get(taskId);
          if (!task) throw fail(`Unknown pending task: ${taskId}`);
          if (task.completed) {
            if (canonicalEvidenceKey(task.result) === canonicalEvidenceKey(saved)) return clone(task.result);
            throw fail(`Task is already completed: ${taskId}`);
          }
          await append({ event: 'complete', taskId, result: saved }); task.completed = true; task.result = saved; return clone(saved);
        });
      },
      async pendingTasks() { await queue; return [...state.tasks.values()].filter(task => !task.completed).map(entry => clone(entry.task)); },
      async summary(options = {}) { await queue; return (await readEvidenceRun(runDir, { ...options, includeRecords: false })).summary; },
      finish() { return serialize(async () => { const at = now(); await append({ event: 'finish', at }); state.finishedAt = at; return { id: loaded.id, finishedAt: at, pendingTasks: [...state.tasks.values()].filter(task => !task.completed).length }; }); },
      async close() { if (closed) return queue; closed = true; await queue; try { await file.close(); } finally { await release(); } },
    };
    return run;
  } catch (error) { await file?.close().catch(() => {}); await release(); throw error; }
}

function matches(observation, options) {
  if (options.type && observation.type !== options.type) return false;
  if (options.taskId && observation.taskId !== options.taskId) return false;
  if (options.id && observation.id !== options.id) return false;
  if (options.query && !json(observation).toLocaleLowerCase().includes(String(options.query).toLocaleLowerCase())) return false;
  if (typeof options.filter === 'function' && !options.filter(observation)) return false;
  return true;
}

/** Read a bounded result page plus whole-run counts. Set limit:Infinity explicitly for full records. */
export async function readEvidenceRun(runDir, options = {}) {
  runDir = path.resolve(runDir);
  const metadata = await readMetadata(runDir);
  const limit = options.limit ?? 20, offset = options.offset ?? 0;
  if (!(limit === Infinity || Number.isSafeInteger(limit) && limit >= 0) || !Number.isSafeInteger(offset) || offset < 0) throw fail('Evidence pagination requires non-negative offset and limit.');
  const records = [], blobs = new Map(), types = Object.create(null), captureStatuses = Object.create(null), finalIds = new Set(), progress = new Map();
  let count = 0, imageCount = 0, captureCount = 0, matching = 0, referencedBytes = 0;
  const countImages = images => {
    for (const ref of Array.isArray(images) ? images : []) {
      if (!object(ref)) continue;
      imageCount += 1;
      if (HEX.test(ref.sha256 || '') && Number.isSafeInteger(ref.size) && ref.size >= 0) { blobs.set(ref.sha256, ref.size); referencedBytes += ref.size; }
    }
  };
  const state = await processJournal(runDir, async observation => {
    count += 1; types[observation.type || 'observation'] = (types[observation.type || 'observation'] || 0) + 1;
    if (observation.type === 'capture') { captureCount += 1; finalIds.add(observation.id); const status = observation.status || 'unspecified'; captureStatuses[status] = (captureStatuses[status] || 0) + 1; }
    if (observation.type === 'capture-progress' && observation.captureId) {
      if (!progress.has(observation.captureId)) progress.set(observation.captureId, []);
      progress.get(observation.captureId).push(...(Array.isArray(observation.images) ? observation.images : []));
    } else countImages(observation.images);
    if (!matches(observation, options)) return;
    if (options.includeRecords !== false && matching >= offset && records.length < limit) records.push(options.fields ? Object.fromEntries(options.fields.filter(key => Object.hasOwn(observation, key)).map(key => [key, observation[key]])) : observation);
    matching += 1;
  });
  for (const [captureId, images] of progress) if (!finalIds.has(captureId)) countImages(images);
  const pendingTasks = [...state.tasks.values()].filter(entry => !entry.completed).map(entry => entry.task);
  return {
    run: metadata,
    summary: { durability: metadata.durability || 'process', observations: count, captures: captureCount, captureStatuses, partialCaptures: captureStatuses.partial || 0, failedCaptures: captureStatuses.failed || 0, cancelledCaptures: captureStatuses.cancelled || 0, incompleteCaptures: [...progress.keys()].filter(id => !finalIds.has(id)).length, imageReferences: imageCount, uniqueImages: blobs.size, duplicateImages: imageCount - blobs.size, referencedImageBytes: referencedBytes, storedImageBytes: [...blobs.values()].reduce((a, b) => a + b, 0), types, pendingTasks: pendingTasks.length, completedTasks: state.tasks.size - pendingTasks.length, finishedAt: state.finishedAt, trailingBytes: state.recovery.trailingBytes?.length || 0, matching, offset, returned: records.length, hasMore: matching > offset + records.length && options.includeRecords !== false },
    records,
    pendingTasks: options.includeTasks === false ? undefined : pendingTasks,
  };
}

async function copyArtifactTree(run, root, value) {
  if (Array.isArray(value)) { const result = []; for (const entry of value) result.push(await copyArtifactTree(run, root, entry)); return result; }
  if (!object(value)) return value;
  if (HEX.test(value.sha256 || '') && typeof value.path === 'string' && Number.isSafeInteger(value.size)) return copyRef(run, root, value);
  const result = {};
  for (const [key, entry] of Object.entries(value)) Object.defineProperty(result, key, { value: await copyArtifactTree(run, root, entry), enumerable: true, configurable: true, writable: true });
  return result;
}

async function copyRef(run, root, ref) {
  if (!object(ref) || typeof ref.path !== 'string') throw fail('Image artifact reference is missing its path.');
  const file = await resolveEvidenceFile(root, ref.path);
  const saved = await run.storeArtifact(file, { extension: ref.extension || path.extname(ref.path).slice(1) || 'bin', mime: ref.mime });
  if (ref.sha256 && ref.sha256 !== saved.sha256 || ref.size !== undefined && ref.size !== saved.size) throw fail(`Artifact identity does not match its source bytes: ${ref.path}`);
  return { ...ref, ...saved };
}

/** Import capture.mjs collections or native runs while preserving source metadata bytes. */
export async function importCaptureCollection(inputDir, { outputDir, resume = false, metadata = {}, onProgress, signal } = {}) {
  const input = await realpath(inputDir);
  const target = await separateOutput(outputDir, [input], 'Import');
  const native = await exists(path.join(input, 'run.json'));
  if (native) await readMetadata(input);
  const sourceName = native ? 'run.json' : 'summary.json';
  const source = await resolveEvidenceFile(input, sourceName);
  const sourceIdentity = await hashFile(source);
  const journalIdentity = native ? await hashFile(await resolveEvidenceFile(input, JOURNAL)) : null;
  const run = await createEvidenceRun({ outputDir: target, resume, metadata: resume ? {} : { ...metadata, importedFrom: { inputDir: input, format: native ? FORMAT : 'capture.mjs', sourceSha256: sourceIdentity.sha256, ...(journalIdentity ? { journalSha256: journalIdentity.sha256 } : {}) } } });
  let imported = 0;
  try {
    const original = run.metadata.importedFrom;
    if (!original || original.inputDir !== input || original.sourceSha256 !== sourceIdentity.sha256 || original.journalSha256 !== journalIdentity?.sha256) throw fail('Import resumption source differs from the original collection.', 'Create another output directory for the changed source.');
    const prior = await readEvidenceRun(run.outputDir, { type: 'import-source', limit: 1 });
    if (!prior.records.length) {
      const artifact = await run.storeArtifact(source, { extension: 'json', mime: 'application/json' });
      let journal;
      if (native) journal = await run.storeArtifact(await resolveEvidenceFile(input, JOURNAL), { extension: 'ndjson', mime: 'application/x-ndjson' });
      await run.record({ id: 'import-source', type: 'import-source', source: { inputDir: input, format: native ? FORMAT : 'capture.mjs', metadata: artifact, ...(journal ? { journal } : {}) } });
    }
    const state = await processJournal(run.outputDir);
    const importOne = async (record, index, copy) => {
      if (signal?.aborted) throw fail('Import interrupted.', 'Resume the same source and output to continue.');
      const taskId = `import:${index}`;
      await run.enqueue({ id: taskId, sourceIndex: index });
      if (state.tasks.get(taskId)?.completed) return;
      const id = native ? `source:${record.id}` : `import-observation:${index}`;
      if (!state.ids.has(id)) await run.record({ ...(await copy(record)), id, ...(native ? { importTaskId: taskId } : { taskId }), sourceIdentity: { run: sourceIdentity.sha256, index, ...(record.id ? { originalId: record.id } : {}) } });
      await run.complete(taskId, { observationId: id });
      imported += 1;
      if (onProgress) await onProgress({ imported, sourceIndex: index });
    };
    if (native) {
      let index = 0;
      for await (const event of iterateEvidenceEvents(input)) {
        if (event.event !== 'observation') continue;
        const record = event.observation;
        await importOne(record, index++, async item => {
          return { ...(await copyArtifactTree(run, input, item)), ...(item.captureId ? { captureId: `source:${item.captureId}` } : {}), ...(item.taskId ? { taskId: `source:${item.taskId}` } : {}), ...(item.type === 'transition' ? { from: typeof item.from === 'string' ? `source:${item.from}` : item.from, to: typeof item.to === 'string' ? `source:${item.to}` : item.to } : {}), sourceObservation: item };
        });
      }
      const nativeState = await processJournal(input);
      for (const [id, entry] of nativeState.tasks) {
        const nativeTaskId = `source:${id}`;
        await run.enqueue({ ...entry.task, id: nativeTaskId, sourceTask: entry.task });
        if (entry.completed) await run.complete(nativeTaskId, entry.result);
      }
      if (nativeState.recovery.trailingBytes?.length && !state.ids.has('import-warning')) await run.record({ id: 'import-warning', type: 'import-warning', label: 'Source has an incomplete trailing journal append', trailingBytes: nativeState.recovery.trailingBytes.length });
    } else {
      let collection;
      try { collection = JSON.parse(await readFile(source, 'utf8')); } catch { throw fail('Capture summary is not valid JSON.'); }
      if (!object(collection) || !Array.isArray(collection.captures)) throw fail('Capture collection requires a captures array in summary.json.');
      for (const [index, capture] of collection.captures.entries()) {
        await importOne(capture, index, async item => {
          if (!object(item) || !Array.isArray(item.images)) throw fail(`Capture ${index} must contain an images array.`);
          const images = [];
          for (const image of item.images) {
            const rel = typeof image === 'string' ? image : image.file;
            const file = await resolveEvidenceFile(input, rel);
            const ref = await run.storeArtifact(file);
            images.push({ ...(object(image) ? image : {}), ...ref, sourceFile: rel });
          }
          return { ...item, type: 'capture', label: item.view || item.report || `Capture ${index + 1}`, state: { report: item.report, view: item.view, hash: item.hash, viewport: item.page?.viewport || { width: item.width, height: collection.options?.height }, scheme: item.scheme, ...(item.url ? { url: item.url } : {}) }, images, sourceCapture: item };
        });
      }
      if (!state.ids.has('import-context')) await run.record({ id: 'import-context', type: 'import-context', source: Object.fromEntries(Object.entries(collection).filter(([key]) => key !== 'captures')) });
    }
    if ((await hashFile(source)).sha256 !== sourceIdentity.sha256 || native && (await hashFile(await resolveEvidenceFile(input, JOURNAL))).sha256 !== journalIdentity.sha256) throw fail('Source collection changed during import.', 'Retain this partial import and create a new output from the settled source.');
    await run.finish();
    const summary = await run.summary();
    return { outputDir: run.outputDir, id: run.id, imported, summary };
  } finally { await run.close(); }
}

export function canonicalEvidenceKey(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalEvidenceKey).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalEvidenceKey(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}

function comparisonKey(record, key) {
  if (key) { const selected = key(record); return selected === undefined || selected === null ? null : `caller:${canonicalEvidenceKey(selected)}`; }
  const explicit = record.comparisonKey ?? record.state?.comparisonKey;
  if (explicit !== undefined) return `explicit:${canonicalEvidenceKey(explicit)}`;
  if (!object(record.state) || !Object.keys(record.state).length) return null;
  const selection = record.selection ?? record.images?.find(image => image.selection)?.selection;
  const selectionFrames = {};
  for (const role of ['subject', 'scrollContainer']) {
    const frame = selection?.[role]?.frame;
    if (frame) selectionFrames[role] = { url: frame.url, name: frame.name, ...(frame.ancestry ? { ancestry: frame.ancestry } : {}) };
  }
  return `state:${canonicalEvidenceKey({ type: record.type, state: record.state, ...(record.target ? { target: record.target } : {}), ...(record.captureScope ? { captureScope: record.captureScope } : {}), ...(Object.keys(selectionFrames).length ? { selectionFrames } : {}) })}`;
}

/** Match only explicit keys or exact recorded states; repeated candidates stay ambiguous. */
export async function compareRuns(leftDir, rightDir, { outputDir, key, ...options } = {}) {
  const left = await readEvidenceRun(leftDir, { type: 'capture', ...options, limit: Infinity });
  const right = await readEvidenceRun(rightDir, { type: 'capture', ...options, limit: Infinity });
  const groups = new Map(), unmatched = { left: [], right: [] };
  const verified = new Map();
  for (const [root, records] of [[leftDir, left.records], [rightDir, right.records]]) for (const record of records) for (const ref of record.images || []) await verifyEvidenceArtifact(root, ref, verified);
  for (const [side, input] of [['left', left], ['right', right]]) for (const record of input.records) {
    const identity = comparisonKey(record, key);
    if (identity === null) { unmatched[side].push(record); continue; }
    if (!groups.has(identity)) groups.set(identity, { left: [], right: [] });
    groups.get(identity)[side].push(record);
  }
  const pairs = [], ambiguous = [];
  for (const [identity, group] of groups) {
    if (group.left.length > 1 || group.right.length > 1) { ambiguous.push({ key: identity, ...group }); continue; }
    if (!group.left.length) { unmatched.right.push(...group.right); continue; }
    if (!group.right.length) { unmatched.left.push(...group.left); continue; }
    const a = group.left[0], b = group.right[0];
    const aHashes = (a.images || []).map(ref => ref.sha256), bHashes = (b.images || []).map(ref => ref.sha256);
    const status = !aHashes.length || !bHashes.length ? 'no-image-comparison' : aHashes.every(value => HEX.test(value || '')) && bHashes.every(value => HEX.test(value || '')) && json(aHashes) === json(bHashes) ? 'identical-bytes' : 'different-bytes';
    pairs.push({ key: identity, status, left: a, right: b });
  }
  const result = { format: 'playwright-evidence-comparison', version: VERSION, leftRun: left.run.id, rightRun: right.run.id, summary: { matched: pairs.length, identical: pairs.filter(pair => pair.status === 'identical-bytes').length, different: pairs.filter(pair => pair.status === 'different-bytes').length, noImages: pairs.filter(pair => pair.status === 'no-image-comparison').length, ambiguous: ambiguous.length, onlyLeft: unmatched.left.length, onlyRight: unmatched.right.length }, pairs, ambiguous, onlyLeft: unmatched.left, onlyRight: unmatched.right };
  if (outputDir) {
    const output = await separateOutput(outputDir, [leftDir, rightDir], 'Comparison');
    const run = await createEvidenceRun({ outputDir: output, metadata: { comparison: { leftRun: left.run, rightRun: right.run } } });
    try {
      const save = async (label, leftRecords, rightRecords, context) => {
        const images = [];
        for (const [side, root, records] of [['left', leftDir, leftRecords], ['right', rightDir, rightRecords]]) for (const record of records) for (const ref of record.images || []) images.push({ ...(await copyRef(run, root, ref)), side, sourceObservationId: record.id });
        await run.record({ type: 'comparison', label, images, context });
      };
      for (const pair of pairs) await save(`${pair.status}: ${pair.left.label || pair.left.id}`, [pair.left], [pair.right], pair);
      for (const group of ambiguous) await save('Ambiguous state match', group.left, group.right, group);
      for (const [side, records] of [['left', unmatched.left], ['right', unmatched.right]]) for (const record of records) await save(`Only ${side}: ${record.label || record.id}`, side === 'left' ? [record] : [], side === 'right' ? [record] : [], { side, record });
      await atomicJson(path.join(run.outputDir, 'comparison.json'), result);
      await run.finish();
    } finally { await run.close(); }
    result.outputDir = output;
  }
  return result;
}
