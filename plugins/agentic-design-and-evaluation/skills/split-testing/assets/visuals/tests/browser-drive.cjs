// Drive a headless Chrome over the DevTools protocol with Node's built-in
// WebSocket and fetch (nothing to install), for what --dump-dom cannot do: an
// exact viewport (headless windows are never narrower than 500 px) and real Tab
// presses. test_browser.py runs it; it prints one JSON line.
//
//   node browser-drive.cjs --chrome PATH --profile DIR --url URL
//        [--width 390] [--height 900] [--script FILE] [--tab-to SELECTOR]
//
// --script FILE holds the body of an async function evaluated in the page once
// the report is ready; its return value is reported as "result". --tab-to
// presses Tab from the top of the page until SELECTOR has focus and reports
// how many presses that took as "tabs" (null when it was never reached).
"use strict";
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf(name); return i >= 0 && args[i + 1] !== undefined ? args[i + 1] : fallback; };
const print = value => process.stdout.write(JSON.stringify(value) + "\n");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  if (typeof WebSocket === "undefined" || typeof fetch === "undefined") { print({ skip: "this Node has no built-in WebSocket and fetch" }); return; }
  const chromePath = option("--chrome"), profile = option("--profile"), url = option("--url");
  if (!chromePath || !profile || !url) { print({ error: "--chrome, --profile and --url are required" }); return; }
  const width = Number(option("--width", "390")), height = Number(option("--height", "900"));
  const script = option("--script") ? fs.readFileSync(option("--script"), "utf8") : "return null;";
  const tabTo = option("--tab-to");
  fs.mkdirSync(profile, { recursive: true });
  const portFile = path.join(profile, "DevToolsActivePort");
  fs.rmSync(portFile, { force: true });
  const flags = ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
    "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"];
  if (typeof process.getuid === "function" && process.getuid() === 0) flags.unshift("--no-sandbox"); // Chrome refuses its sandbox as root
  const chrome = spawn(chromePath, flags, { stdio: "ignore" });
  const exited = new Promise(resolve => chrome.once("exit", resolve));
  let ws;
  try {
    let port = "";
    for (let i = 0; i < 150 && !port; i++) { await sleep(100); try { port = fs.readFileSync(portFile, "utf8").split("\n")[0].trim(); } catch { /* not yet written */ } }
    if (!port) throw new Error("Chrome did not open a DevTools port within 15 seconds");
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const page = targets.find(t => t.type === "page");
    if (!page) throw new Error("Chrome has no page target");
    ws = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = () => reject(new Error("the DevTools socket did not open")); });
    let next = 0;
    const pending = new Map();
    ws.onmessage = event => { const m = JSON.parse(event.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
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
    await send("Page.navigate", { url });
    let ready = false;
    for (let i = 0; i < 200 && !ready; i++) { await sleep(50); try { ready = await evaluate("!!document.querySelector('[data-av-ready]')"); } catch { /* navigating */ } }
    if (!ready) throw new Error("the report never became ready");
    await sleep(300);
    const out = { width: await evaluate("innerWidth"), result: await evaluate(`(async () => { ${script} })()`) };
    if (tabTo) {
      await evaluate("document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); true");
      const key = type => send("Input.dispatchKeyEvent", { type, key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
      out.tabs = null;
      for (let presses = 1; presses <= 600; presses++) {
        await key("rawKeyDown"); await key("keyUp");
        if (await evaluate(`!!document.activeElement && document.activeElement.matches(${JSON.stringify(tabTo)})`)) { out.tabs = presses; break; }
      }
    }
    print(out);
  } catch (error) {
    print({ error: error instanceof Error ? error.message : String(error) });
  } finally {
    try { ws?.close(); } catch { /* already closed */ }
    chrome.kill();
    await Promise.race([exited, sleep(5000)]);
  }
}

main();
