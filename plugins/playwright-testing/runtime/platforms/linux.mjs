import { randomBytes } from 'node:crypto';
import { spawn } from 'node:child_process';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { findExecutable, ownProcess } from '../lifecycle.mjs';
import { runtimeError } from '../resolution.mjs';

// Xauthority's FamilyWild entry is private to this run. Xvfb reads the cookie
// at startup; clients can use it after the readiness FD reveals the display.
function authorityBytes() {
  const fields = [Buffer.alloc(0), Buffer.alloc(0), Buffer.from('MIT-MAGIC-COOKIE-1'), randomBytes(16)];
  const family = Buffer.alloc(2); family.writeUInt16BE(65535);
  return Buffer.concat([family, ...fields.flatMap(field => { const length = Buffer.alloc(2); length.writeUInt16BE(field.length); return [length, field]; })]);
}

export function x11Environment(env, { display, authority }) {
  const child = { ...env, DISPLAY: display, XAUTHORITY: authority, XDG_SESSION_TYPE: 'x11', GDK_BACKEND: 'x11', QT_QPA_PLATFORM: 'xcb', SDL_VIDEODRIVER: 'x11', MOZ_ENABLE_WAYLAND: '0', ELECTRON_OZONE_PLATFORM_HINT: 'x11', OZONE_PLATFORM: 'x11' };
  delete child.WAYLAND_DISPLAY;
  delete child.WAYLAND_SOCKET;
  return child;
}

export async function acquireXvfb({ directory, env, display, timeout = 15000, executable }) {
  const binary = executable ?? await findExecutable('Xvfb', env);
  if (!binary) throw runtimeError('XVFB_MISSING', 'Isolated headed execution needs Xvfb on Linux.', 'Install the optional Xvfb system package, select headless, or configure an isolated session provider.');
  const authority = join(directory, 'Xauthority');
  await writeFile(authority, authorityBytes(), { mode: 0o600, flag: 'wx' });
  const child = spawn(binary, ['-displayfd', '3', '-screen', '0', `${display.width}x${display.height}x24`, '-nolisten', 'tcp', '-auth', authority, '-noreset'], { env, detached: true, stdio: ['ignore', 'ignore', 'pipe', 'pipe'] });
  let spawnError;
  child.on('error', error => { spawnError = error; });
  let stderr = '';
  child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-2000); });
  const exited = new Promise(resolve => child.once('close', resolve));
  const close = async () => {
    if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
    child.kill('SIGTERM');
    let timer;
    await Promise.race([exited, new Promise(resolve => { timer = setTimeout(resolve, 1500); })]);
    clearTimeout(timer);
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    await exited;
  };
  try {
    await ownProcess(directory, { pid: child.pid, kind: 'xvfb', group: true });
    if (spawnError) throw runtimeError('XVFB_START_FAILED', 'The private Xvfb process could not start.', 'Check the Xvfb executable and its system dependencies.', spawnError);
    const number = await new Promise((resolve, reject) => {
      let buffer = '';
      const fail = () => reject(runtimeError('XVFB_START_FAILED', 'The private Xvfb display did not become ready.', 'Check Xvfb availability, screen dimensions, and the runtime diagnostics.'));
      const timer = setTimeout(fail, timeout);
      const cleanup = () => { clearTimeout(timer); child.removeListener('error', onError); child.removeListener('exit', onExit); child.stdio[3].removeListener('data', onData); };
      const onError = error => { cleanup(); reject(runtimeError('XVFB_START_FAILED', 'The private Xvfb process could not start.', 'Check the Xvfb executable and its system dependencies.', error)); };
      const onExit = () => { cleanup(); fail(); };
      const onData = bytes => {
        buffer += bytes.toString();
        if (!buffer.includes('\n')) return;
        cleanup();
        const number = buffer.trim();
        if (!/^\d+$/.test(number)) reject(runtimeError('XVFB_READINESS_INVALID', 'Xvfb returned an invalid display identifier.'));
        else resolve(number);
      };
      child.once('error', onError); child.once('exit', onExit); child.stdio[3].on('data', onData);
    });
    const displayName = `:${number}`;
    return { backend: 'xvfb', renderingOS: 'linux', env: x11Environment(env, { display: displayName, authority }), info: { display: displayName, screen: display, authorization: 'private-cookie' }, close };
  } catch (error) { await close(); throw error; }
}
