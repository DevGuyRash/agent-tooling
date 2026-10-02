"""Hidden driver for async-sync-contract-py. Runs inside the check's sandbox (no network, host read-only, its
own PID namespace, /tmp and /run private), as /usr/bin/python3 -I driver.py CODE SCRATCH < config.json.

For each fxd state it serves a fake fxd on a Unix socket (or leaves a missing or stale socket), runs the
agent's shelftag through the callers in callers/ as separate processes with FXD_SOCKET set (or unset, for the
documented default path), and prints one JSON verdict line with every process's exit status and output and
the requests each fake fxd received. It decides nothing; check.py compares the outputs with the reference.

States (every OK reply is dated the day it is sent, in UTC as the callers' TZ is, so a client that accepts
only today's rate and one that takes whatever fxd gives both get the rate, whenever the check runs):
  up        FXD_SOCKET=/tmp/fxd/up.sock, replies OK with the main rate
  up2       FXD_SOCKET=/tmp/fxd/up2.sock, replies OK with another rate (six places)
  default   FXD_SOCKET unset, fxd at /run/fxd/fxd.sock with a third rate
  err       FXD_SOCKET=/tmp/fxd/err.sock, replies ERR
  refused   FXD_SOCKET=/tmp/fxd/stale.sock, a socket file left by a crashed fxd: bound, never listening
  missing   FXD_SOCKET=/tmp/fxd/missing.sock, no such file
A request other than "RATE CHF EUR" gets "ERR not understood" and is logged as malformed.
"""
import json
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CALLERS = HERE / "callers"
CODE, SCRATCH = sys.argv[1], Path(sys.argv[2])
PY = sys.executable
LIMIT = 60
REQUEST = "RATE CHF EUR"


def today():
    return datetime.now(timezone.utc).date().isoformat()


class FakeFxd:
    """fxd on a Unix socket; reply is the line it answers RATE CHF EUR with, {today} filled in per request."""
    def __init__(self, path, reply):
        self.path, self.reply, self.requests, self.lock = path, reply, [], threading.Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fxd = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(5)
                data = b""
                try:
                    while b"\n" not in data and len(data) < 512:
                        chunk = self.request.recv(512)
                        if not chunk:
                            break
                        data += chunk
                except OSError:
                    pass
                line = data.split(b"\n", 1)[0].decode("utf-8", "replace").rstrip("\r")
                with fxd.lock:
                    fxd.requests.append(line)
                try:
                    answer = fxd.reply.format(today=today()) if line == REQUEST else "ERR not understood"
                    self.request.sendall((answer + "\n").encode())
                except OSError:
                    pass

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True
            request_queue_size = 512  # a daemon's ordinary listen backlog: the docs set no limit on clients

        self.server = Server(path, Handler)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


class Stale:
    """A socket file a crashed fxd left behind: bound, never listening, so connecting is refused."""
    def __init__(self, path):
        self.path, self.requests = path, []
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)

    def close(self):
        self.sock.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


class Nothing:
    requests = []

    def close(self):
        pass


def start(state, rates):
    """(daemon, FXD_SOCKET value or None for unset) for one fxd state."""
    if state == "up":
        return FakeFxd("/tmp/fxd/up.sock", f"OK {rates['up']} {{today}}"), "/tmp/fxd/up.sock"
    if state == "up2":
        return FakeFxd("/tmp/fxd/up2.sock", f"OK {rates['up2']} {{today}}"), "/tmp/fxd/up2.sock"
    if state == "default":
        return FakeFxd("/run/fxd/fxd.sock", f"OK {rates['default']} {{today}}"), None
    if state == "err":
        return FakeFxd("/tmp/fxd/err.sock", "ERR no CHF/EUR rate for {today}"), "/tmp/fxd/err.sock"
    if state == "refused":
        return Stale("/tmp/fxd/stale.sock"), "/tmp/fxd/stale.sock"
    if state == "missing":
        return Nothing(), "/tmp/fxd/missing.sock"
    raise ValueError(state)


def env_for(fxd_socket):
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "TMPDIR": "/tmp", "LANG": "C.UTF-8",
           "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": f"{CODE}:{CODE}/src",
           "PYTHONIOENCODING": "utf-8"}
    if fxd_socket is not None:
        env["FXD_SOCKET"] = fxd_socket
    return env


def run(argv, env):
    start_t = time.monotonic()
    try:
        r = subprocess.run(argv, env=env, cwd=CODE, stdin=subprocess.DEVNULL, capture_output=True, timeout=LIMIT)
        rc, out, err = r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        rc, out, err = None, (exc.stdout or b"").decode("utf-8", "replace"), "time limit reached"
    result = {"rc": rc, "seconds": round(time.monotonic() - start_t, 3), "stderr": err[-600:]}
    try:
        result["json"] = json.loads(out.strip().splitlines()[-1]) if out.strip() else None
    except ValueError:
        result["json"] = None
    result["stdout"] = out[-20000:]
    return result


def main():
    config = json.load(sys.stdin)
    cases_path = SCRATCH / "cases.json"
    cases_path.write_text(json.dumps(config["cases"]), encoding="utf-8")
    items_csv = SCRATCH / "items.csv"
    items_csv.write_text(config["items_csv"], encoding="utf-8")
    verdict = {"plain": {}, "callers": {}, "api": None, "requests": {}}
    for state in config["plain_states"] + [s for s in config["caller_states"] if s not in config["plain_states"]]:
        daemon, fxd_socket = start(state, config["rates"])
        try:
            env = env_for(fxd_socket)
            if state in config["plain_states"]:
                verdict["plain"][state] = run([PY, str(CALLERS / "probe_plain.py"), str(cases_path)], env)
                verdict["requests"][f"plain-{state}"] = list(daemon.requests)
                daemon.requests.clear()
            if state == config["api_state"]:
                verdict["api"] = run([PY, str(CALLERS / "probe_api.py")], env)
            if state in config["caller_states"]:
                for caller in ("pos_sync", "webshop", "labeld"):
                    verdict["callers"][f"{caller}-{state}"] = run([PY, str(CALLERS / f"{caller}.py"), str(cases_path)], env)
                verdict["callers"][f"cli-{state}"] = run([PY, "-m", "shelftag", "print", str(items_csv)], env)
            verdict["requests"][f"other-{state}"] = list(daemon.requests)
        finally:
            daemon.close()
    print(json.dumps(verdict))


main()
