"""Hidden driver for async-fanout-go. Runs inside a bubblewrap sandbox with its own network and PID namespaces.

usage: python3 driver.py < CONFIG_JSON   (prints one JSON verdict as its last line)

It starts a SCADA gateway on 127.0.0.1 inside the sandbox (docs/gateway.md: one request line per connection,
LIST and READ, at most `limit` connections at a time, a connection over the limit closed without a reply),
runs one command against it with the gateway's address in the configured environment variable, waits for
the command to exit (killing it at `hard_limit` seconds), keeps the gateway listening for `linger` seconds
to see whether anything still arrives, kills every process left in the sandbox, and only then prints its
verdict, so nothing the command left behind can write after it. With `steps` in the configuration it instead
runs the command once per step, each with the step's arguments and environment ("{gateway}" in them is the
gateway's address, "{down}" an address nothing listens on) and its own time limit, one after another.

A connection counts from the moment it is accepted until the gateway starts sending its reply, or until the
client closes it. A client that shuts down only its sending side has hung up too, as docs/gateway.md says
(and internal/fakegw does): the gateway cannot tell that from a close, and drops the request. When a
connection arrives the gateway first drops every counted connection whose client has hung up, and before
refusing one for being over the limit it keeps doing so for up to GRACE seconds, so a client that closes a
connection and at once opens another is never counted, or refused, for the old one. A refused connection's
request line is read (when the client sends it within REFUSED_READ seconds) only to record which inverter
was asked for; the client gets no reply either way. The verdict also counts the connections that stayed
counted longer than `held_after` seconds while the command ran (a connection the client neither got a reply
on nor closed). The configuration comes on standard input, so nothing in the sandbox can read the dataset
from this process later.
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

GRACE = 0.05          # see the module docstring
REFUSED_READ = 0.2    # seconds to wait for a refused connection's request line, for the record only
REQUEST_WAIT = 10.0   # seconds a connection may stay open without sending its request line
LIST_LATENCY = 0.01


class Gateway:
    def __init__(self, cfg):
        self.inverters = {d["name"]: d for d in cfg["inverters"]}
        self.order = cfg["order"]
        self.limit = cfg["limit"]
        self.hold = cfg["hold"]
        self.lock = threading.Lock()
        self.active = {}        # id(entry) -> (entry, connection)
        self.log = []           # one entry per connection
        self.t0 = time.monotonic()
        self.exited = None      # when the command exited, relative to t0
        self.refused = 0
        self.peak = 0           # most connections counted at once
        self.demand = 0         # most the client tried to have open at once (refused ones included)
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
        if self.active.pop(id(entry), None) is not None:
            entry["end"] = round(self.now(), 4)
            entry["outcome"] = outcome

    def begin(self, conn, entry):
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
                    return True
                if time.monotonic() >= deadline:
                    self.demand = max(self.demand, n + 1)
                    self.refused += 1
                    entry["end"], entry["outcome"] = round(self.now(), 4), "refused"
                    return False
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
                entry = {"request": None, "start": round(self.now(), 4), "end": None, "outcome": None,
                         "late": self.exited is not None}
                self.log.append(entry)
            threading.Thread(target=self._serve, args=(conn, entry), daemon=True).start()

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
                time.sleep(min(left, 0.02))  # the client sent more than its one line; keep waiting
        return True

    def _serve(self, conn, entry):
        try:
            if not self.begin(conn, entry):
                entry["request"] = read_line(conn, REFUSED_READ)
                return
            line = read_line(conn, REQUEST_WAIT)
            entry["request"] = line
            if line is None:
                self.finish(entry, "no request")
                return
            reply = self._handle(conn, line)
            if reply is None:
                self.finish(entry, "abandoned")
                return
            self.finish(entry, "answered " + reply.split(" ", 2)[1 if reply.startswith("ERR") else 0])
            try:
                conn.sendall(reply.encode())
            except OSError:
                pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _handle(self, conn, line):
        verb, _, name = line.partition(" ")
        if verb == "LIST" and not name:
            if not self._wait(conn, LIST_LATENCY):
                return None
            return f"OK {len(self.order)}\n" + "".join(n + "\n" for n in self.order)
        if verb != "READ" or not name:
            return "ERR 400 bad request\n" if self._wait(conn, 0.01) else None
        inv = self.inverters.get(name)
        if inv is None:
            return "ERR 404 unknown inverter\n" if self._wait(conn, 0.03) else None
        if inv["kind"] == "offline":
            return "ERR 504 inverter timeout\n" if self._wait(conn, self.hold) else None
        if not self._wait(conn, inv["latency"]):
            return None
        if inv["kind"] == "error":
            return f"ERR {inv['error']}\n"
        return f"OK {name} {inv['wh']} {inv['w']}\n"

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def stats(self, held_after):
        with self.lock:
            log = [dict(e) for e in self.log]
            exited = self.exited if self.exited is not None else round(self.now(), 4)
        # How long each connection the command opened was counted while it ran (up to its exit, when the
        # kernel closes whatever it still held); "held" ones stayed counted longer than held_after.
        spans = [min(exited if e["end"] is None else e["end"], exited) - e["start"]
                 for e in log if not e["late"] and e["outcome"] != "refused"]
        per_inverter, lists = {}, 0
        for e in log:
            verb, _, name = (e["request"] or "").partition(" ")
            if verb == "READ" and name:  # refused connections count: the client asked
                per_inverter[name] = per_inverter.get(name, 0) + 1
            elif verb == "LIST":
                lists += 1
        return {"connections": len(log), "refused": self.refused, "peak": self.peak, "demand": self.demand,
                "held": sum(1 for s in spans if s > held_after), "longest": round(max(spans, default=0.0), 3),
                "late_connections": sum(1 for e in log if e["late"]),
                "abandoned": sum(1 for e in log if e["outcome"] == "abandoned"),
                "no_request": sum(1 for e in log if e["outcome"] == "no request"),
                "list_requests": lists, "reads_per_inverter": per_inverter, "exited": self.exited,
                "log": [[e["request"], e["start"], e["end"], e["outcome"]] for e in log[:2000]]}


def read_line(conn, timeout):
    """The connection's request line without its newline, or None at EOF, on garbage, or after timeout."""
    buf, end = b"", time.monotonic() + timeout
    while b"\n" not in buf:
        left = end - time.monotonic()
        if left <= 0 or len(buf) > 4096:
            return None
        try:
            readable, _, _ = select.select([conn], [], [], left)
            if not readable:
                return None
            chunk = conn.recv(4096)
        except (OSError, ValueError):
            return None
        if not chunk:
            return None
        buf += chunk
    return buf.split(b"\n", 1)[0].decode("utf-8", "replace").strip()


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
    # What the command can see of the machine: the CPUs it may run on (what Go's runtime.NumCPU reports).
    machine = {"cpus_available": len(os.sched_getaffinity(0)), "port": port}
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
