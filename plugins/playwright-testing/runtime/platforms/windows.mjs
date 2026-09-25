import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { atomicJSON, delay, findExecutable, ownProcess } from '../lifecycle.mjs';
import { runtimeError } from '../resolution.mjs';

export async function acquireWindowsWorker({ directory, options, env }) {
  const powershell = await findExecutable('powershell.exe', env) ?? await findExecutable('pwsh.exe', env);
  if (!powershell) throw runtimeError('POWERSHELL_MISSING', 'Private Windows desktop execution needs PowerShell.', 'Enable Windows PowerShell or supply a configured isolated session provider.');
  const configPath = join(directory, 'windows-worker.json');
  const nodeWorker = fileURLToPath(new URL('../supervisor.mjs', import.meta.url));
  const config = { ...options, directory, privateWorker: true };
  await atomicJSON(configPath, config);
  const desktopConfig = { command: process.execPath, args: [nodeWorker, '--private-worker', configPath], cwd: options.projectDir, env, desktop: `PlaywrightSurvey_${options.token}`, parentPid: process.pid };
  const desktopConfigPath = join(directory, 'windows-desktop.json');
  await atomicJSON(desktopConfigPath, desktopConfig);
  const helper = spawn(powershell, ['-NoLogo', '-NoProfile', '-NonInteractive', '-File', fileURLToPath(new URL('./private-desktop.ps1', import.meta.url)), '-ConfigPath', desktopConfigPath], { env, windowsHide: true, stdio: ['ignore', 'inherit', 'inherit'] });
  const exited = new Promise(resolve => { helper.once('exit', (code, signal) => resolve({ code, signal })); helper.once('error', () => resolve({ code: 1, signal: null })); });
  await ownProcess(directory, { pid: helper.pid, kind: 'windows-desktop-helper' });
  let failure = false;
  helper.on('exit', () => { failure = true; }); helper.on('error', () => { failure = true; });
  const readMessage = async (name, timeout = 30000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      try { return JSON.parse(await readFile(join(directory, name), 'utf8')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
      if (failure) throw runtimeError('WINDOWS_DESKTOP_FAILED', 'The private Windows desktop worker exited before readiness.', 'Check the native helper diagnostics and Windows desktop access.');
      await delay(40);
    }
    throw runtimeError('WINDOWS_DESKTOP_TIMEOUT', 'The private Windows desktop worker did not become ready.', 'Check Windows desktop access and browser installation.');
  };
  const close = async () => {
    await atomicJSON(join(directory, 'windows-control.json'), { close: true });
    let timer;
    await Promise.race([exited, new Promise(resolve => { timer = setTimeout(resolve, 5000); })]); clearTimeout(timer);
    if (!failure) helper.kill();
    await exited;
  };
  try {
    const message = await readMessage('windows-ready.json', options.startupTimeout ?? 30000);
    if (message.type === 'error') throw runtimeError(message.code, message.message, message.hint);
    return { ...message, backend: 'win32-private-desktop', renderingOS: 'win32', info: { ...message.info, desktop: desktopConfig.desktop, nativeQualification: 'pending' }, completion: () => readMessage('windows-result.json', options.timeout ?? 86400000), close };
  } catch (error) { await close(); throw error; }
}
