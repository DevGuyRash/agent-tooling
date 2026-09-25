import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { constants } from 'node:fs';
import { access, chmod, lstat, mkdir, mkdtemp, readFile, readdir, realpath, rename, rm, rmdir, writeFile } from 'node:fs/promises';
import { hostname, tmpdir } from 'node:os';
import { basename, join, resolve } from 'node:path';
import { runtimeError } from './resolution.mjs';

export const OWNERSHIP_FORMAT = 'playwright-survey-resources/1';
const TEMPORARY_FORMAT = 'playwright-survey-temporary/1';
const TEMPORARY_MARKER = '.playwright-survey-owner.json';
export const OWNER_ENV = 'PLAYWRIGHT_SURVEY_OWNER';
export const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function atomicJSON(path, value) {
  const temporary = `${path}.${randomBytes(6).toString('hex')}.tmp`;
  try {
    await writeFile(temporary, JSON.stringify(value), { mode: 0o600, flag: 'wx' });
    await rename(temporary, path);
  } finally { await rm(temporary, { force: true }); }
}

export async function processIdentity(pid) {
  if (!Number.isInteger(pid) || pid < 2) return null;
  try {
    process.kill(pid, 0);
    if (process.platform === 'linux') {
      const stat = await readFile(`/proc/${pid}/stat`, 'utf8');
      const fields = stat.slice(stat.lastIndexOf(')') + 2).split(' ');
      if (fields[0] === 'Z') return null;
      return { pid, started: fields[19] };
    }
    if (process.platform === 'darwin') {
      const result = spawnSync('ps', ['-p', String(pid), '-o', 'lstart='], { encoding: 'utf8' });
      if (result.status === 0 && result.stdout.trim()) return { pid, started: result.stdout.trim() };
      return null;
    }
    // Windows process handles/Job Objects provide the strong lifetime boundary.
    return { pid, started: null };
  } catch { return null; }
}

export async function identityAlive(identity) {
  if (!identity) return false;
  const current = await processIdentity(identity.pid);
  return !!current && (identity.started === null || current.started === identity.started);
}

async function assertPrivateDirectory(path, { create = false } = {}) {
  if (create) await mkdir(path, { recursive: true, mode: 0o700 });
  const stat = await lstat(path);
  if (!stat.isDirectory() || stat.isSymbolicLink() || (process.getuid && stat.uid !== process.getuid())) throw runtimeError('RESOURCE_OWNERSHIP', 'The resource directory is not an owned directory.', 'Choose an ordinary directory owned by the current user.');
  if (process.platform !== 'win32' && stat.mode & 0o077) throw runtimeError('RESOURCE_PERMISSIONS', 'The resource directory is accessible to other users.', 'Choose a private directory with mode 0700.');
}

export async function createOwnedRun(root, { temporaryRoot } = {}) {
  const resourceRoot = resolve(root ?? join(tmpdir(), `playwright-survey-${process.getuid?.() ?? 'user'}`));
  await assertPrivateDirectory(resourceRoot, { create: true });
  const directory = await mkdtemp(join(resourceRoot, 'run-'));
  await chmod(directory, 0o700);
  const record = { format: OWNERSHIP_FORMAT, id: basename(directory), token: randomBytes(24).toString('hex'), host: hostname(), uid: process.getuid?.() ?? null, owner: await processIdentity(process.pid), supervisor: null, resources: [], createdAt: new Date().toISOString() };
  let temporaryCreated = false;
  try {
    // AF_UNIX limits apply to browser-created sockets, independently of how
    // long the selected evidence/ownership paths may be. Ignore inherited
    // TMPDIR for this short-lived allocation; it may itself be a project path.
    const base = resolve(temporaryRoot ?? (process.platform === 'win32' ? (process.env.LOCALAPPDATA ? join(process.env.LOCALAPPDATA, 'Temp') : tmpdir()) : '/tmp'));
    await mkdir(base, { recursive: true, mode: 0o700 });
    record.temporaryDirectory = join(await realpath(base), `pws-${record.token.slice(0, 16)}`);
    if (process.platform !== 'win32' && Buffer.byteLength(record.temporaryDirectory) > 48) throw runtimeError('TEMPORARY_PATH_TOO_LONG', 'The selected temporaryRoot leaves insufficient space for browser socket paths.', 'Choose a shorter temporaryRoot, such as /tmp; resourceRoot and artifactDir can remain at their requested locations.');
    // Persist the reserved path before creating it so an interrupted allocation
    // remains discoverable from the selected resource root.
    await atomicJSON(join(directory, 'ownership.json'), record);
    await mkdir(record.temporaryDirectory, { mode: 0o700 });
    temporaryCreated = true;
    await writeFile(join(record.temporaryDirectory, TEMPORARY_MARKER), JSON.stringify({ format: TEMPORARY_FORMAT, token: record.token, host: record.host, uid: record.uid, resourceDirectory: directory }), { mode: 0o600, flag: 'wx' });
    return { directory, root: resourceRoot, record };
  } catch (error) {
    if (temporaryCreated) await rm(record.temporaryDirectory, { recursive: true, force: true });
    await rm(directory, { recursive: true, force: true });
    if (error.code === 'TEMPORARY_PATH_TOO_LONG') throw error;
    throw runtimeError('TEMPORARY_SETUP_FAILED', 'The private browser temporary directory could not be created.', 'Use a writable short temporaryRoot; keep retained evidence in artifactDir.', error);
  }
}

function validateTemporaryPath(record) {
  const path = record.temporaryDirectory;
  if (typeof path !== 'string' || resolve(path) !== path || basename(path) !== `pws-${record.token.slice(0, 16)}`) throw runtimeError('TEMPORARY_OWNERSHIP', 'The browser temporary-directory association could not be verified.', 'Preserve the ownership record and inspect the named temporary directory before cleanup.');
  return path;
}

export async function readOwnedTemporary(directory, record) {
  const path = validateTemporaryPath(record);
  await assertPrivateDirectory(path);
  try {
    const markerPath = join(path, TEMPORARY_MARKER), stat = await lstat(markerPath);
    if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('Invalid temporary-directory marker.');
    const marker = JSON.parse(await readFile(markerPath, 'utf8'));
    if (marker.format !== TEMPORARY_FORMAT || marker.token !== record.token || marker.host !== record.host || marker.uid !== record.uid || marker.resourceDirectory !== resolve(directory)) throw new Error('Temporary-directory marker does not match.');
    return path;
  } catch (error) { throw runtimeError('TEMPORARY_OWNERSHIP', 'The browser temporary-directory owner marker could not be verified.', 'Preserve the ownership record and inspect the named temporary directory before cleanup.', error); }
}

export async function readOwnedRun(directory) {
  await assertPrivateDirectory(directory);
  const path = join(directory, 'ownership.json');
  const stat = await lstat(path);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('Invalid ownership file.');
  const record = JSON.parse(await readFile(path, 'utf8'));
  if (record.format !== OWNERSHIP_FORMAT || record.id !== basename(directory) || record.host !== hostname() || record.uid !== (process.getuid?.() ?? null) || !/^[a-f0-9]{48}$/.test(record.token) || !Array.isArray(record.resources)) throw new Error('Unrecognized ownership record.');
  return record;
}

export async function ownProcess(directory, resource) {
  const record = await readOwnedRun(directory);
  const identity = await processIdentity(resource.pid);
  if (!identity) return;
  record.resources.push({ ...identity, kind: resource.kind, group: resource.group === true });
  await atomicJSON(join(directory, 'ownership.json'), record);
}

export async function ownedLinuxProcesses(token) {
  if (process.platform !== 'linux') return [];
  const marker = Buffer.from(`${OWNER_ENV}=${token}\0`);
  const processes = [];
  for (const entry of await readdir('/proc')) {
    if (!/^\d+$/.test(entry) || Number(entry) === process.pid) continue;
    try {
      const info = await lstat(`/proc/${entry}`);
      if (process.getuid && info.uid !== process.getuid()) continue;
      const environment = await readFile(`/proc/${entry}/environ`);
      const match = environment.indexOf(marker);
      if (match < 0 || (match > 0 && environment[match - 1] !== 0)) continue;
      const identity = await processIdentity(Number(entry));
      if (identity) processes.push(identity);
    } catch { /* Processes may exit during enumeration. */ }
  }
  return processes;
}

export async function terminateOwned(directory, { grace = 1500 } = {}) {
  const record = await readOwnedRun(directory);
  const identities = process.platform === 'linux' ? await ownedLinuxProcesses(record.token) : record.resources;
  const signal = async name => {
    if (process.platform === 'linux') for (const resource of record.resources.filter(item => item.group)) {
      // A verified detached leader owns its process group, including sandboxed
      // browser children whose environment may be unreadable through /proc.
      if (!identities.some(item => item.pid === resource.pid) || !await identityAlive(resource)) continue;
      try {
        const stat = await readFile(`/proc/${resource.pid}/stat`, 'utf8');
        const fields = stat.slice(stat.lastIndexOf(')') + 2).split(' ');
        if (Number(fields[2]) === resource.pid && Number(fields[3]) === resource.pid) process.kill(-resource.pid, name);
      } catch { /* The verified group already exited. */ }
    }
    for (const identity of identities) {
      if (identity.pid === process.pid || !await identityAlive(identity)) continue;
      if (process.platform === 'win32') continue;
      let pid = identity.pid;
      if (process.platform === 'darwin' && identity.group) {
        const group = spawnSync('ps', ['-p', String(identity.pid), '-o', 'pgid='], { encoding: 'utf8' });
        if (Number(group.stdout?.trim()) === identity.pid) pid = -identity.pid;
      }
      try { process.kill(pid, name); } catch { /* Already exited. */ }
    }
  };
  await signal('SIGTERM');
  const deadline = Date.now() + grace;
  while (Date.now() < deadline && (await Promise.all(identities.map(identityAlive))).some(Boolean)) await delay(30);
  await signal('SIGKILL');
}

export async function removeOwnedRun(directory) {
  const record = await readOwnedRun(directory);
  if (record.temporaryDirectory) {
    const temporary = validateTemporaryPath(record);
    try {
      await readOwnedTemporary(directory, record);
      await rm(temporary, { recursive: true, force: true });
    } catch (error) {
      if (error.code !== 'ENOENT') {
        // A crash between mkdir and writing its marker can leave an empty
        // reserved directory. rmdir removes it only while it is still empty.
        if (error.code === 'TEMPORARY_OWNERSHIP' && error.cause?.code === 'ENOENT') await rmdir(temporary);
        else throw error;
      }
    }
  }
  await rm(directory, { recursive: true, force: true });
}

export async function recoverOwnedResources(root, { grace = 2000, dryRun = false } = {}) {
  const resourceRoot = resolve(root ?? join(tmpdir(), `playwright-survey-${process.getuid?.() ?? 'user'}`));
  const result = { recovered: [], active: [], skipped: [], ...(dryRun ? { dryRun: true, wouldRecover: [] } : {}) };
  try { await assertPrivateDirectory(resourceRoot); } catch (error) { if (error.code === 'ENOENT') return result; throw error; }
  for (const entry of await readdir(resourceRoot, { withFileTypes: true })) {
    if (!entry.isDirectory() || !entry.name.startsWith('run-')) continue;
    const directory = join(resourceRoot, entry.name);
    let record;
    try { record = await readOwnedRun(directory); } catch { result.skipped.push({ id: entry.name, reason: 'ownership could not be verified' }); continue; }
    if (await identityAlive(record.owner)) { result.active.push(entry.name); continue; }
    if (record.provider && record.cleanup?.status === 'incomplete') { result.skipped.push({ id: entry.name, reason: 'provider teardown needs recovery using its retained identity' }); continue; }
    if (process.platform === 'win32' && (await Promise.all(record.resources.map(identityAlive))).some(Boolean)) { result.skipped.push({ id: entry.name, reason: 'Windows process lifetime needs native confirmation; retaining ownership record' }); continue; }
    if (dryRun) { result.wouldRecover.push(entry.name); continue; }
    if (await identityAlive(record.supervisor)) {
      if (process.platform === 'win32') { result.skipped.push({ id: entry.name, reason: 'live Windows supervisor; native Job Object owns cleanup' }); continue; }
      try { process.kill(record.supervisor.pid, 'SIGTERM'); } catch { /* Already exited. */ }
      const deadline = Date.now() + grace;
      while (Date.now() < deadline && await identityAlive(record.supervisor)) await delay(30);
    }
    try {
      await terminateOwned(directory, { grace });
      await removeOwnedRun(directory);
      result.recovered.push(entry.name);
    } catch (error) { if (error.code === 'ENOENT') result.recovered.push(entry.name); else result.skipped.push({ id: entry.name, reason: 'cleanup incomplete; preserve ownership record for retry' }); }
  }
  return result;
}

export async function findExecutable(name, env = process.env) {
  const separator = process.platform === 'win32' ? ';' : ':';
  const paths = name.includes('/') || name.includes('\\') ? [''] : (env.PATH ?? '').split(separator);
  const extensions = process.platform === 'win32' && !/\.[a-z]+$/i.test(name) ? (env.PATHEXT ?? '.EXE;.CMD;.BAT').split(';') : [''];
  for (const directory of paths) for (const extension of extensions) {
    const candidate = directory ? join(directory, name + extension) : name + extension;
    try { await access(candidate, process.platform === 'win32' ? constants.F_OK : constants.X_OK); return resolve(candidate); } catch { /* Try next path. */ }
  }
  return null;
}
