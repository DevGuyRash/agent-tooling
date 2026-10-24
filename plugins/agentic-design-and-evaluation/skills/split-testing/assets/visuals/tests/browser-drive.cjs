// Drive a headless Chromium-family browser (Chrome, Chromium, Edge, Brave) over
// the DevTools protocol with Node's built-in WebSocket and fetch (nothing to
// install), for what --dump-dom cannot do: an exact viewport (headless windows
// are never narrower than 500 px) and real Tab presses. test_browser.py runs it;
// it prints one JSON line.
//
//   node browser-drive.cjs --browser PATH --profile DIR --url URL
//        [--width 390] [--height 900] [--script FILE] [--tab-to SELECTOR]
//
// When the drive ends the browser is asked to close itself (Browser.close),
// which removes its singleton folder from the temp directory; a killed browser,
// or a killed wrapper such as firejail, flatpak or snap, leaves that folder for
// good. The drive waits for the browser's whole process group to end, signals
// it only when it has not, and always finishes with a kill of whatever the
// launcher left in that group; a browser that did not close itself has the
// singleton folder its profile's SingletonSocket link names removed, unless
// the link named it before this launch. The JSON
// line says how the browser stopped ("stopped": "closed", "terminated" or
// "killed") and names its singleton folder ("singleton", null when the browser
// keeps no link to one) for the caller to check. SIGTERM, SIGINT or SIGHUP to
// this driver stops the browser the same way before it exits. test_browser.py removes the empty fetcher
// folder a short-lived browser also leaves in the temp directory.
//
// --script FILE holds the body of an async function evaluated in the page once
// the report is ready; its return value is reported as "result". The script may
// call avDriveResize("WIDTHxHEIGHT") to have the window resized, as a reader
// resizing it would, and wait for the page's resize event. --tab-to
// presses Tab from the top of the page until SELECTOR has focus and reports
// how many presses that took as "tabs" (null when it was never reached).
"use strict";
const { execFileSync, spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf(name); return i >= 0 && args[i + 1] !== undefined ? args[i + 1] : fallback; };
const print = value => process.stdout.write(JSON.stringify(value) + "\n");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const within = (ms, promise) => Promise.race([promise, sleep(ms).then(() => { throw new Error("timed out"); })]);

// [process group, state] of every process: from /proc where it lists this one
// (Linux, a slim container without ps included), else from ps; null when
// neither answers.
function processes() {
  try {
    const pids = fs.readdirSync("/proc").filter(name => /^\d+$/.test(name));
    if (pids.includes(String(process.pid))) return pids.flatMap(pid => {
      try { const stat = fs.readFileSync(`/proc/${pid}/stat`, "utf8"); const [state, , pgid] = stat.slice(stat.lastIndexOf(")") + 2).split(" "); return [[Number(pgid), state]]; }
      catch { return []; } // ended while listed
    });
  } catch { /* no /proc */ }
  try {
    return execFileSync("ps", ["-A", "-o", "pgid=", "-o", "stat="], { encoding: "utf8", timeout: 5000, killSignal: "SIGKILL" }).trim().split("\n")
      .map(row => { const [pgid, stat] = row.trim().split(/\s+/); return [Number(pgid), stat || ""]; });
  } catch { return null; }
}

async function stop(browser, port) {
  // The browser has ended when nothing that can still run is left in its
  // process group (where groups exist), not merely when its launcher, which may
  // be a wrapper, exits. An exited member nobody has reaped yet (a zombie, as
  // under a container init that does not reap) does not count.
  const running = () => {
    if (process.platform === "win32") return browser.exitCode === null && browser.signalCode === null;
    try { process.kill(-browser.pid, 0); } catch { return false; }
    const all = processes(); // null: the group still exists, so it counts as running
    return all === null || all.some(([pgid, state]) => pgid === browser.pid && !state.startsWith("Z"));
  };
  const ended = async ms => { for (const end = Date.now() + ms; Date.now() < end; await sleep(100)) if (!running()) return true; return !running(); };
  const group = signal => { try { process.kill(-browser.pid, signal); } catch { try { browser.kill(signal); } catch { /* already gone */ } } };
  let outcome = "killed";
  if (port) {
    try {
      await within(6000, (async () => {
        const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
        const socket = new WebSocket(version.webSocketDebuggerUrl);
        await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = () => reject(new Error("the browser socket did not open")); });
        socket.send(JSON.stringify({ id: 1, method: "Browser.close" }));
      })());
      if (await ended(10000)) outcome = "closed";
    } catch { /* no DevTools endpoint left to ask */ }
  }
  if (outcome !== "closed") {
    group("SIGTERM");
    if (await ended(5000)) outcome = "terminated";
  }
  group("SIGKILL"); // whatever the launcher left in its group, even after a clean close
  await ended(5000);
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
  const singletonFolder = () => { try { return path.dirname(fs.readlinkSync(path.join(profile, "SingletonSocket"))); } catch { return null; } };
  const before = singletonFolder(); // another browser's, or a stale one: never this launch's to remove
  const browser = spawn(browserPath, flags, { stdio: "ignore", detached: process.platform !== "win32" });
  let ws, out, port = "", singleton = null, stopping = null;
  // Stop the browser once, and remove the singleton folder of one that did not
  // close itself, keeping a folder that holds more than its Singleton* entries.
  const finish = () => (stopping ??= stop(browser, port).then(outcome => {
    const folder = outcome === "closed" ? null : singleton ?? singletonFolder();
    try { if (folder && folder !== before && path.isAbsolute(folder) && fs.readdirSync(folder).every(name => name.startsWith("Singleton"))) fs.rmSync(folder, { recursive: true, force: true }); } catch { /* already gone */ }
    return outcome;
  }));
  for (const signal of ["SIGTERM", "SIGINT", "SIGHUP"]) process.once(signal, () => finish().finally(() => process.exit(1)));
  try {
    for (let i = 0; i < 150 && !port; i++) { await sleep(100); try { port = fs.readFileSync(portFile, "utf8").split("\n")[0].trim(); } catch { /* not yet written */ } }
    if (!port) throw new Error("the browser did not open a DevTools port within 15 seconds");
    singleton = singletonFolder();
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
    out.stopped = await finish();
    out.singleton = singleton;
    print(out);
  }
}

main();
