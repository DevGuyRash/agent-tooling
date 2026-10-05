#!/usr/bin/env python3
"""One owned page target in an existing Chromium process, for native visual checks.

The helper attaches to an already-running Chrome DevTools endpoint, creates one
page target and closes it again. It never launches a browser or installs
anything; raw CDP needs the `websocket-client` package to be present already.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

# Render one Mermaid diagram as a complete report through the public API, then
# wait until its scene settles. `key` names a global that keeps the enhancement
# so the next call can clean it up; `width` fixes the report container's width.
MOUNT_DIAGRAM = """async(key,{title,source,theme='light',width=null})=>{
  globalThis[key]?.cleanup();
  document.documentElement.setAttribute('data-theme',theme);
  const holder=document.createElement('div');
  holder.innerHTML=AgenticVisuals.renderReport({title,sections:[{id:'qualification',title,blocks:[{type:'diagram',title,source}]}]});
  const root=holder.firstElementChild;if(!root)throw Error('renderReport returned no root');
  if(width){root.style.width=width;root.style.maxWidth='none';}
  document.body.replaceChildren(root);
  const enhanced=AgenticVisuals.enhance(root);globalThis[key]=enhanced;
  await enhanced.diagrams?.whenIdle();
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  await enhanced.diagrams?.whenIdle();
  return root;
}"""

# A generated report has mounted and every diagram in it has settled.
REPORT_READY = (
    "document.readyState==='complete' && typeof AgenticVisuals==='object' && "
    "!!document.querySelector('[data-av-report][data-av-ready]') && "
    "[...document.querySelectorAll('[data-av-mermaid]')].every(e=>['ready','error'].includes(e.getAttribute('data-av-mermaid-state')))"
)
# The same, for a report that embeds Mermaid so MOUNT_DIAGRAM can draw.
DIAGRAM_REPORT_READY = REPORT_READY + " && typeof mermaid==='object'"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def normalized_endpoint(value: str) -> str:
    value = value.strip().rstrip("/")
    if "://" not in value:
        value = "http://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--cdp must be an HTTP(S) Chrome DevTools endpoint")
    return value


def read_json(url: str, *, method: str = "GET") -> dict:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


class NativePage:
    """One owned page target in an existing Chrome process."""

    def __init__(self, endpoint: str):
        import websocket  # websocket-client; imported here so REPORT_READY users need not have it

        self.endpoint = normalized_endpoint(endpoint)
        created = read_json(self.endpoint + "/json/new?about:blank", method="PUT")
        self.target_id = created["id"]
        self.socket = websocket.create_connection(created["webSocketDebuggerUrl"], suppress_origin=True, timeout=45)
        self.sequence = 0
        self.events: list[dict] = []
        for method in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            self.call(method)
        self.call("Emulation.setFocusEmulationEnabled", enabled=True)

    def call(self, method: str, **params):
        self.sequence += 1
        request_id = self.sequence
        self.socket.send(json.dumps({"id": request_id, "method": method, "params": params}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression: str):
        result = self.call("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            description = details.get("exception", {}).get("description") or details.get("text") or str(details)
            preview = " ".join(expression.strip().split())[:420]
            raise RuntimeError(f"{description}; expression={preview}")
        return result.get("result", {}).get("value")

    def viewport(self, width: int, height: int) -> None:
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)

    def navigate(self, path: Path) -> None:
        url = path.resolve().as_uri() + "?native-check=1"
        self.call("Page.navigate", url=url)
        self.wait("location.href.split('#')[0] === " + json.dumps(url) + " && document.readyState === 'complete'", timeout=30)

    def wait(self, expression: str, *, timeout: float = 20, interval: float = 0.05):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = self.evaluate(expression)
            if last:
                return last
            time.sleep(interval)
        raise TimeoutError(f"Timed out waiting for {expression}; last={last!r}")

    def settle(self) -> None:
        self.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
        time.sleep(0.05)

    def screenshot(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.call("Page.captureScreenshot", format="png", fromSurface=True)
        path.write_bytes(base64.b64decode(payload["data"]))
        return str(path)

    def console_errors(self) -> list[dict]:
        errors = []
        for event in self.events:
            if event.get("method") == "Runtime.exceptionThrown":
                errors.append(event)
            elif event.get("method") == "Log.entryAdded" and event.get("params", {}).get("entry", {}).get("level") == "error":
                errors.append(event)
        return errors

    def close(self) -> None:
        try:
            self.socket.close()
        finally:
            try:
                read_json(self.endpoint + "/json/close/" + self.target_id)
            except Exception:
                pass
