import { readFile, readlink, readdir, realpath, stat } from 'node:fs/promises';
import { basename } from 'node:path';

/** Verify the Linux fixture's requested headed run stays on an owned Xvfb display. */
export async function assertQuietEnvironment(env = process.env) {
  if (process.platform !== 'linux') throw new Error('This supplied fixture targets Linux native qualification; use its Linux evaluation environment.');
  const hint = 'Run the command on an owned private Xvfb display with private XAUTHORITY, preserve EVAL_PRIMARY_DISPLAY, and clear WAYLAND_DISPLAY for the child.';
  const fail = reason => { throw new Error(`${reason}\nhint: ${hint}`); };
  if (!Object.hasOwn(env, 'EVAL_PRIMARY_DISPLAY')) fail('EVAL_PRIMARY_DISPLAY is missing; it must identify the original host display (an empty original value is allowed).');
  const display = env.DISPLAY ?? '';
  const match = /^:(\d+)(?:\.\d+)?$/.exec(display);
  if (!match) fail('A private local X11 display is required before this headed test launches.');
  const primary = /^:(\d+)(?:\.\d+)?$/.exec(env.EVAL_PRIMARY_DISPLAY ?? '');
  if (primary && Number(primary[1]) === Number(match[1])) fail('DISPLAY still points to the original host display.');
  if (env.WAYLAND_DISPLAY) fail('WAYLAND_DISPLAY still points to a host session.');
  if (!env.XAUTHORITY) fail('Private display authorization is missing.');
  let displayPid, authority;
  try {
    authority = await realpath(env.XAUTHORITY);
    const authorityStat = await stat(authority);
    if (!authorityStat.isFile() || authorityStat.uid !== process.getuid() || (authorityStat.mode & 0o077)) fail('XAUTHORITY must be a private regular file owned by this user.');
    // Xvfb's readiness-FD allocation can omit the legacy .X<N>-lock file.
    // Establish the owner through the kernel's listening Unix socket instead.
    const address = `/tmp/.X11-unix/X${Number(match[1])}`;
    const inodes = new Set((await readFile('/proc/net/unix', 'utf8')).split('\n').flatMap(line => {
      const fields = line.trim().split(/\s+/);
      return fields[7] === address || fields[7] === '@' + address ? [fields[6]] : [];
    }));
    if (!inodes.size) fail('The requested private display has no listening Unix socket.');
    for (const pid of await readdir('/proc')) {
      if (!/^\d+$/.test(pid)) continue;
      try {
        if ((await stat(`/proc/${pid}`)).uid !== process.getuid()) continue;
        const argv = (await readFile(`/proc/${pid}/cmdline`, 'utf8')).split('\0').filter(Boolean);
        if (basename(argv[0] ?? '') !== 'Xvfb') continue;
        const authIndex = argv.indexOf('-auth');
        if (authIndex < 0 || await realpath(argv[authIndex + 1]) !== authority) continue;
        let ownsSocket = false;
        for (const fd of await readdir(`/proc/${pid}/fd`)) {
          const link = await readlink(`/proc/${pid}/fd/${fd}`).catch(() => '');
          const socket = /^socket:\[(\d+)\]$/.exec(link);
          if (socket && inodes.has(socket[1])) { ownsSocket = true; break; }
        }
        if (ownsSocket) { displayPid = Number(pid); break; }
      } catch { /* A process may exit during observation. */ }
    }
    if (!displayPid) fail('The private display socket is not owned by this user’s matching Xvfb process.');
  } catch (error) {
    if (error.message.includes('\nhint:')) throw error;
    fail('Cannot verify the private Xvfb process and its authorization file.');
  }
  return { display, displayPid, authority, waylandPresent: false, backend: 'xvfb', ownershipObservation: 'listening Unix socket and private authorization' };
}
