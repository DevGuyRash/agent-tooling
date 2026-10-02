"""Hidden driver for async-fanout-py. Runs inside a bubblewrap sandbox with its own network and PID namespaces.

usage: python3 driver.py < CONFIG_JSON   (prints one JSON verdict as its last line)

It starts a dock gateway on 127.0.0.1 inside the sandbox (docs/gateway-api.md: GET /v1/docks and
GET /v1/docks/{id}/status, at most `limit` requests in progress per client, 429 beyond that), runs one
command against it with the gateway's URL in the configured environment variable, waits for the command to
exit (killing it at `hard_limit` seconds), keeps the gateway listening for `linger` seconds to see whether
anything still arrives, kills every process left in the sandbox, and only then prints its verdict, so
nothing the command left behind can write after it. With `steps` in the configuration it instead runs the
command once per step, each with the step's arguments and environment ("{gateway}" in them is the gateway's
URL, "{down}" a URL nothing listens on) and its own time limit, one after another.

A request is in progress from the moment its headers have arrived until the gateway starts sending its
response, or until the client closes the connection. When a request arrives the gateway first drops every
request in progress whose client has hung up, and before refusing one for being over the limit it keeps
doing so for up to GRACE seconds, so a client that closes a connection and at once opens another is never
counted, or refused, for the old one. The verdict also counts the requests that stayed in progress longer
than `held_after` seconds while the command ran (a request the client neither got an answer to nor hung up
on). The configuration comes on standard input, so nothing in the sandbox can read the dataset from this
process later.
"""
import json
import os
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

REASONS = {200: "OK", 404: "Not Found", 429: "Too Many Requests", 500: "Internal Server Error",
           502: "Bad Gateway", 504: "Gateway Timeout"}
LIST_LATENCY = 0.02
# Before refusing a request for being over the limit, the gateway keeps looking this long for requests whose
# client has hung up: a client that closes one connection and opens the next on another CPU can have the new
# request read before the old connection's end has been processed.
GRACE = 0.05


class Gateway:
    def __init__(self, cfg):
        self.docks = {d["id"]: d for d in cfg["docks"]}
        self.order = cfg["order"]
        self.limit = cfg["limit"]
        self.hold = cfg["hold"]
        self.lock = threading.Lock()
        self.active = {}        # id(entry) -> (entry, connection)
        self.log = []           # one entry per request
        self.t0 = time.monotonic()
        self.exited = None      # when the command exited, relative to t0
        self.refused = 0
        self.peak = 0           # most requests in progress at once
        self.demand = 0         # most the client tried to have in progress at once (refused ones included)
        self.late_connections = 0
        self.connections = 0
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1024)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def now(self):
        return time.monotonic() - self.t0

    # -- bookkeeping

    def _gone(self, conn):
        """True when the client has closed the connection (EOF or reset waiting to be read)."""
        try:
            return conn.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b""
        except BlockingIOError:
            return False
        except OSError:
            return True

    def _end(self, entry, outcome):
        """Take entry out of progress (once); caller holds the lock."""
        if self.active.pop(id(entry), None) is not None:
            entry["end"] = round(self.now(), 4)
            entry["outcome"] = outcome

    def begin(self, conn, path):
        with self.lock:
            entry = {"path": path, "start": round(self.now(), 4), "end": None, "outcome": None,
                     "late": self.exited is not None}
            self.log.append(entry)
        deadline = time.monotonic() + GRACE
        while True:
            with self.lock:
                for other, other_conn in list(self.active.values()):
                    if self._gone(other_conn):
                        self._end(other, "abandoned")
                n = len(self.active)
                if n < self.limit:
                    self.active[id(entry)] = (entry, conn)
                    self.peak = max(self.peak, n + 1)
                    self.demand = max(self.demand, n + 1)
                    return entry
                if time.monotonic() >= deadline:
                    self.demand = max(self.demand, n + 1)
                    self.refused += 1
                    entry["end"], entry["outcome"] = round(self.now(), 4), "refused"
                    return None
            time.sleep(0.005)

    def finish(self, entry, outcome):
        with self.lock:
            self._end(entry, outcome)

    def mark_exit(self):
        with self.lock:
            self.exited = round(self.now(), 4)
            return len(self.active)

    # -- serving

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with self.lock:
                self.connections += 1
                if self.exited is not None:
                    self.late_connections += 1
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _wait(self, conn, seconds):
        """Wait `seconds`; False as soon as the client hangs up."""
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            try:
                readable, _, _ = select.select([conn], [], [], left)
            except (OSError, ValueError):
                return False
            if readable:
                if self._gone(conn):
                    return False
                time.sleep(min(left, 0.02))  # the client sent more (pipelining); keep waiting
        return True

    def _serve(self, conn):
        buf = b""
        try:
            while True:
                request, buf = read_request(conn, buf)
                if request is None:
                    return
                method, path, close = request
                entry = self.begin(conn, path)
                if entry is None:
                    send(conn, 429, {"error": "too many requests in progress"}, close)
                    if close:
                        return
                    continue
                status, body = self._handle(conn, method, path)
                if status is None:
                    self.finish(entry, "abandoned")
                    return
                self.finish(entry, f"answered {status}")
                if not send(conn, status, body, close) or close:
                    return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _handle(self, conn, method, path):
        parts = path.split("?", 1)[0].strip("/").split("/")
        if method != "GET":
            return (404, {"error": "not found"}) if self._wait(conn, LIST_LATENCY) else (None, None)
        if parts == ["v1", "docks"]:
            if not self._wait(conn, LIST_LATENCY):
                return None, None
            return 200, {"docks": [{"id": d, "name": self.docks[d]["name"]} for d in self.order]}
        if len(parts) == 4 and parts[:2] == ["v1", "docks"] and parts[3] == "status":
            dock = self.docks.get(parts[2])
            if dock is None:
                return (404, {"error": "no such dock"}) if self._wait(conn, 0.03) else (None, None)
            if dock["kind"] == "offline":
                return (504, {"error": "dock did not answer"}) if self._wait(conn, self.hold) else (None, None)
            if not self._wait(conn, dock["latency"]):
                return None, None
            if dock["kind"] == "failed":
                return dock["status"], {"error": "dock fault"}
            return 200, {"id": dock["id"], "bikes": dock["bikes"], "free": dock["free"],
                         "read_at": "2026-10-01T06:00:00Z", "firmware": "4.2.1"}
        return (404, {"error": "not found"}) if self._wait(conn, 0.01) else (None, None)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def stats(self, held_after):
        with self.lock:
            log = [dict(e) for e in self.log]
            exited = self.exited if self.exited is not None else round(self.now(), 4)
        per_dock = {}
        for e in log:
            parts = e["path"].split("?", 1)[0].strip("/").split("/")
            if len(parts) == 4 and parts[3] == "status":  # refused requests count: the client asked
                per_dock[parts[2]] = per_dock.get(parts[2], 0) + 1
        # How long each request the command made was in progress while it ran (up to its exit, when the
        # kernel closes whatever it still held); "held" ones stayed in progress longer than held_after.
        spans = [min(exited if e["end"] is None else e["end"], exited) - e["start"]
                 for e in log if not e["late"] and e["outcome"] != "refused"]
        return {"requests": len(log), "refused": self.refused, "peak": self.peak, "demand": self.demand,
                "held": sum(1 for s in spans if s > held_after), "longest": round(max(spans, default=0.0), 3),
                "late_requests": sum(1 for e in log if e["late"]), "late_connections": self.late_connections,
                "connections": self.connections, "abandoned": sum(1 for e in log if e["outcome"] == "abandoned"),
                "list_requests": sum(1 for e in log if e["path"].split("?", 1)[0].strip("/") == "v1/docks"),
                "status_per_dock": per_dock, "exited": self.exited,
                "log": [[e["path"].rsplit("/", 2)[-2] if e["path"].endswith("/status") else e["path"],
                         e["start"], e["end"], e["outcome"]] for e in log[:2000]]}


def read_request(conn, buf):
    """((method, path, close), rest) for the next request on conn, or (None, b"") at EOF or on garbage."""
    while b"\r\n\r\n" not in buf:
        if len(buf) > 65536:
            return None, b""
        try:
            chunk = conn.recv(65536)
        except OSError:
            return None, b""
        if not chunk:
            return None, b""
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    try:
        method, path, version = lines[0].split(" ", 2)
    except ValueError:
        return None, b""
    headers = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    length = int(headers.get("content-length", "0") or 0)
    while len(rest) < length:
        try:
            chunk = conn.recv(65536)
        except OSError:
            return None, b""
        if not chunk:
            return None, b""
        rest += chunk
    close = headers.get("connection", "").lower() == "close" or version.upper() == "HTTP/1.0"
    return (method, path, close), rest[length:]


def send(conn, status, body, close):
    data = json.dumps(body).encode()
    head = (f"HTTP/1.1 {status} {REASONS.get(status, 'Error')}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(data)}\r\n" + ("Connection: close\r\n" if close else "") + "\r\n")
    try:
        conn.sendall(head.encode() + data)
        return True
    except OSError:
        return False


def live_processes():
    me, found = os.getpid(), []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) in (1, me):
            continue
        try:
            stat = Path("/proc", entry, "stat").read_bytes()
            cmd = Path("/proc", entry, "cmdline").read_bytes()
        except OSError:
            continue
        if stat[stat.rfind(b")") + 2:].split()[0] in (b"Z", b"X"):
            continue
        found.append((int(entry), cmd.replace(b"\0", b" ").decode(errors="replace").strip()[:200]))
    return found


def kill_everything():
    for _ in range(50):
        procs = live_processes()
        if not procs:
            return
        for pid, _ in procs:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.05)


def run_one(cmd, cwd, env, limit, out_path, err_path):
    """(exit status, killed, seconds) for one run of cmd; at `limit` seconds its process group is killed."""
    with open(out_path, "wb") as out, open(err_path, "wb") as err:
        started = time.monotonic()
        # A session of its own (so a process group of its own), so a time-out kills all of it.
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                start_new_session=True)
        try:
            rc, killed = proc.wait(timeout=limit), False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            rc, killed = proc.wait(), True
    return rc, killed, round(time.monotonic() - started, 3)


def dead_port():
    with socket.socket() as s:  # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    cfg = json.loads(sys.stdin.read())
    scratch = Path(cfg["scratch"])
    scratch.mkdir(parents=True, exist_ok=True)
    gw = None if cfg.get("down") else Gateway(cfg)
    port = gw.port if gw else dead_port()
    addrs = {"gateway": cfg["gateway_format"].format(port=port), "down": cfg["gateway_format"].format(port=dead_port())}
    # What the command can see of the machine: the CPUs it may run on, and the count Python reports (which
    # PYTHON_CPU_COUNT in the configured environment fixes on Python 3.13 and later).
    machine = {"cpus_available": len(os.sched_getaffinity(0)), "cpu_count": os.cpu_count(), "port": port}
    if cfg.get("steps") is not None:
        steps = []
        for i, step in enumerate(cfg["steps"]):
            env = dict(cfg["env"])
            env.update({k: v.format(**addrs) for k, v in step.get("env", {}).items()})
            out_path, err_path = scratch / f"stdout-{i}", scratch / f"stderr-{i}"
            rc, killed, elapsed = run_one(cfg["cmd"] + [a.format(**addrs) for a in step["args"]], cfg["cwd"], env,
                                          step["limit"], out_path, err_path)
            steps.append({"rc": rc, "killed": killed, "elapsed": elapsed,
                          "stdout": out_path.read_bytes().decode("utf-8", "replace")[:20000],
                          "stderr": err_path.read_bytes().decode("utf-8", "replace")[-2000:]})
        survivors = [cmd for _, cmd in live_processes()]
        kill_everything()
        if gw:
            gw.close()
        sys.stdout.write("\n" + json.dumps({"steps": steps, "survivors": survivors[:20], **machine}) + "\n")
        sys.stdout.flush()
        return
    env = dict(cfg["env"])
    env[cfg["gateway_env"]] = addrs["gateway"]
    out_path, err_path = scratch / "stdout", scratch / "stderr"
    rc, killed, elapsed = run_one(cfg["cmd"], cfg["cwd"], env, cfg["hard_limit"], out_path, err_path)
    in_progress_at_exit = gw.mark_exit() if gw else 0
    time.sleep(cfg["linger"])
    survivors = [cmd for _, cmd in live_processes()]
    kill_everything()
    if gw:
        time.sleep(0.1)
        gw.close()
    verdict = {"rc": rc, "killed": killed, "elapsed": elapsed, "survivors": survivors[:20],
               "in_progress_at_exit": in_progress_at_exit,
               "stdout": out_path.read_bytes().decode("utf-8", "replace")[:200000],
               "stderr": err_path.read_bytes().decode("utf-8", "replace")[-4000:],
               "server": gw.stats(cfg["held_after"]) if gw else None, **machine}
    sys.stdout.write("\n" + json.dumps(verdict) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
