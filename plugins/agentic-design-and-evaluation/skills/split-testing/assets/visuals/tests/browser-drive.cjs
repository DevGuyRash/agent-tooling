// Drive a headless Chromium-family browser (Chrome, Chromium, Edge, Brave) over
// the DevTools protocol with Node's built-in WebSocket and fetch (nothing to
// install), for what --dump-dom cannot do: an exact viewport (headless windows
// are never narrower than 500 px) and real Tab presses. test_browser.py runs it;
// it prints one JSON line.
//
//   node browser-drive.cjs --browser PATH --profile DIR --url URL
//        [--width 390] [--height 900] [--script FILE] [--tab-to SELECTOR]
//
// The browser leaves nothing behind. When the drive ends it is asked to close
// itself (Browser.close), which removes its singleton folder from the temp
// directory; a killed browser, or a killed wrapper such as firejail, flatpak or
// snap, leaves that folder for good. Only a browser that has not exited is
// signalled, as a whole process group. A browser with a DevTools port open also
// leaves an empty <app-id>.<name>_url_fetcher_.* folder in the temp directory
// that it never removes, so the drive removes those that appeared while it ran
// and are still empty. The JSON line says how the browser stopped ("stopped":
// "closed", "terminated", "killed", or "exited" when it had already gone) and
// lists in "left" any of its singleton folder that still exists afterwards.
// SIGTERM, SIGINT or SIGHUP to this driver stops the browser the same way first.
//
// --script FILE holds the body of an async function evaluated in the page once
// the report is ready; its return value is reported as "result". The script may
// call avDriveResize("WIDTHxHEIGHT") to have the window resized, as a reader
// resizing it would, and wait for the page's resize event. --tab-to
// presses Tab from the top of the page until SELECTOR has focus and reports
// how many presses that took as "tabs" (null when it was never reached).
"use strict";
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf(name); return i >= 0 && args[i + 1] !== undefined ? args[i + 1] : fallback; };
const print = value => process.stdout.write(JSON.stringify(value) + "\n");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const within = (ms, promise) => Promise.race([promise, sleep(ms).then(() => { throw new Error("timed out"); })]);

// Where a browser puts temp folders: its TMPDIR, or /tmp when a wrapper such as
// firejail strips that variable.
const TEMP_ROOTS = [...new Set([os.tmpdir(), "/tmp"])];
const FETCHER_LEFTOVER = /^(?:com|org)\.[\w-]+\.[\w-]+\.\w*url_fetcher_\.\w+$/;

function fetcherLeftovers() {
  const found = new Set();
  for (const root of TEMP_ROOTS) {
    let names;
    try { names = fs.readdirSync(root); } catch { continue; }
    for (const name of names) if (FETCHER_LEFTOVER.test(name)) found.add(path.join(root, name));
  }
  return found;
}

// Remove the fetcher folders that appeared since `before` and are still empty;
// rmdir refuses a folder that holds anything, so one in use by another browser
// keeps what it holds.
function removeFetcherLeftovers(before, since) {
  for (const folder of fetcherLeftovers()) {
    if (before.has(folder)) continue;
    try {
      const stat = fs.lstatSync(folder);
      if (!stat.isDirectory() || stat.mtimeMs < since || (typeof process.getuid === "function" && stat.uid !== process.getuid())) continue;
      fs.rmdirSync(folder);
    } catch { /* gone, not empty, or not ours */ }
  }
}

async function stop(browser, exited, port) {
  if (browser.exitCode !== null || browser.signalCode !== null) return "exited";
  const gone = ms => Promise.race([exited.then(() => true), sleep(ms).then(() => false)]);
  if (port) {
    try {
      await within(6000, (async () => {
        const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
        const socket = new WebSocket(version.webSocketDebuggerUrl);
        await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = () => reject(new Error("the browser socket did not open")); });
        socket.send(JSON.stringify({ id: 1, method: "Browser.close" }));
      })());
      if (await gone(5000)) return "closed";
    } catch { /* no DevTools endpoint left to ask */ }
  }
  const group = signal => { try { process.kill(-browser.pid, signal); } catch { browser.kill(signal); } };
  group("SIGTERM");
  const outcome = await gone(5000) ? "terminated" : "killed";
  group("SIGKILL"); // whatever the launcher left in its group
  await gone(5000);
  return outcome;
}

async function main() {
  if (typeof WebSocket === "undefined" || typeof fetch === "undefined") { print({ skip: "this Node has no built-in WebSocket and fetch" }); return; }
  const browserPath = option("--browser"), profile = option("--profile"), url = option("--url");
  if (!browserPath || !profile || !url) { print({ error: "--browser, --profile and --url are required" }); return; }
  const width = Number(option("--width", "390")), height = Number(option("--height", "900"));
  const script = option("--script") ? fs.readFileSync(option("--script"), "utf8") : "return null;";
  const tabTo = option("--tab-to");
  fs.mkdirSync(profile, { recursive: true });
  const portFile = path.join(profile, "DevToolsActivePort");
  fs.rmSync(portFile, { force: true });
  const flags = ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
    "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"];
  if (typeof process.getuid === "function" && process.getuid() === 0) flags.unshift("--no-sandbox"); // Chromium refuses its sandbox as root
  const startedAt = Date.now() - 1000, before = fetcherLeftovers();
  const browser = spawn(browserPath, flags, { stdio: "ignore", detached: process.platform !== "win32" });
  const exited = new Promise(resolve => browser.once("exit", resolve));
  let ws, out, port = "", singleton = null, stopping = null;
  const finish = async () => {
    const stopped = await stop(browser, exited, port);
    removeFetcherLeftovers(before, startedAt);
    return stopped;
  };
  for (const signal of ["SIGTERM", "SIGINT", "SIGHUP"]) process.once(signal, () => (stopping ??= finish()).finally(() => process.exit(1)));
  try {
    for (let i = 0; i < 150 && !port; i++) { await sleep(100); try { port = fs.readFileSync(portFile, "utf8").split("\n")[0].trim(); } catch { /* not yet written */ } }
    if (!port) throw new Error("the browser did not open a DevTools port within 15 seconds");
    try { singleton = path.dirname(fs.readlinkSync(path.join(profile, "SingletonSocket"))); } catch { /* this browser keeps no singleton link */ }
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const page = targets.find(t => t.type === "page");
    if (!page) throw new Error("the browser has no page target");
    ws = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = () => reject(new Error("the DevTools socket did not open")); });
    let next = 0;
    const pending = new Map();
    let resize = null;
    ws.onmessage = event => {
      const m = JSON.parse(event.data);
      if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
      else if (m.method === "Runtime.bindingCalled" && m.params.name === "avDriveResize") resize?.(m.params.payload);
    };
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++next;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out`)); }, 20000);
      pending.set(id, m => { clearTimeout(timer); m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result); });
      ws.send(JSON.stringify({ id, method, params }));
    });
    const evaluate = async expression => {
      const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    };
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    await send("Runtime.enable"); await send("Runtime.addBinding", { name: "avDriveResize" });
    resize = payload => { const [w, h] = String(payload).split("x").map(Number); if (w > 0 && h > 0) send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false }).catch(() => {}); };
    await send("Page.navigate", { url });
    let ready = false;
    for (let i = 0; i < 200 && !ready; i++) { await sleep(50); try { ready = await evaluate("!!document.querySelector('[data-av-ready]')"); } catch { /* navigating */ } }
    if (!ready) throw new Error("the report never became ready");
    await sleep(300);
    out = { width: await evaluate("innerWidth"), result: await evaluate(`(async () => { ${script} })()`) };
    if (tabTo) {
      await evaluate("document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); true");
      const key = type => send("Input.dispatchKeyEvent", { type, key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
      out.tabs = null;
      for (let presses = 1; presses <= 600; presses++) {
        await key("rawKeyDown"); await key("keyUp");
        if (await evaluate(`!!document.activeElement && document.activeElement.matches(${JSON.stringify(tabTo)})`)) { out.tabs = presses; break; }
      }
    }
  } catch (error) {
    out = { error: error instanceof Error ? error.message : String(error) };
  } finally {
    try { ws?.close(); } catch { /* already closed */ }
    out.stopped = await (stopping ??= finish());
    out.left = singleton && fs.existsSync(singleton) ? [singleton] : [];
    print(out);
  }
}

main();
