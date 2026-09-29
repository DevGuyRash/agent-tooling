"""Hidden stress probe for eventspool's documented flush()/close()/submit() guarantees.

Run from the root of a copy of the repository under test:  python3 stress_probe.py
Prints one line `PROBE_RESULT {json}` and exits 0 only when every round holds.

It widens the race window deterministically instead of waiting for an unlucky schedule:
- time.sleep is made near-instant before the package is imported, so no sleep in the code under
  test (of any length, however it is imported) can stand in for synchronization;
- probe sinks hold the write that contains the last submitted event open on a gate for longer than
  any plausible fixed wait, and record, at the moment flush()/close() returns, whether that write
  had finished;
- one round pauses the writer right after its queue bookkeeping reaches zero unfinished tasks, which
  widens the gap between "taken off the queue" and "written" in queue.Queue-based designs;
- the parallel round adds a tiny thread switch interval and a sink with real per-write latency;
- the README's background writer is kept: submitted events must reach the sink with no flush() or
  close(), and every sink.write() call is recorded with its thread, so a write made in a caller's
  thread (the probe's own threads or the main thread) is reported.
Every wait is bounded, and the process ends with os._exit so a stuck writer cannot hang it.
"""
import collections
import json
import os
import queue
import random
import sys
import threading
import time

_real_sleep = time.sleep


def _near_instant_sleep(seconds):
    _real_sleep(0 if seconds <= 0 else min(seconds, 1e-4))


time.sleep = _near_instant_sleep
sys.path.insert(0, os.getcwd())

RESULTS = {}
CURRENT_ROUND = {"name": "start"}
CALLER_WRITES = []  # "round: thread" for every sink.write() made in a probe (caller) thread
FLUSH_HOLDS = (0.4, 0.4, 3.0)  # the last cycle catches fixed waits (Event.wait(t), join(t)) up to 3 s


def probe_thread(target, name):
    t = threading.Thread(target=target, name="probe-" + name, daemon=True)
    t.start()
    return t


class ProbeSink:
    """Records completed writes; holds chosen writes open until `gate` opens; flags overlapping writes."""

    def __init__(self, hold_if=None, latency=None):
        self._lock = threading.Lock()
        self._done = []
        self._active = 0
        self.overlap = False
        self.hold_if = hold_if
        self.latency = latency
        self.gate = threading.Event()
        self.held = threading.Event()

    def write(self, events):
        events = list(events)
        t = threading.current_thread()
        if t is threading.main_thread() or t.name.startswith("probe-"):
            CALLER_WRITES.append(f"{CURRENT_ROUND['name']}: {t.name}")
        with self._lock:
            self._active += 1
            if self._active > 1:
                self.overlap = True
        try:
            if self.hold_if is not None and self.hold_if(events):
                self.held.set()
                if not self.gate.wait(20):
                    raise RuntimeError("probe gate never opened")
            if self.latency is not None:
                _real_sleep(self.latency())
            with self._lock:
                self._done.extend(events)
        finally:
            with self._lock:
                self._active -= 1

    def done(self):
        with self._lock:
            return list(self._done)


class Call:
    """Run fn in a probe thread; at the moment it returns, record the sink's state and gate."""

    def __init__(self, fn, sink=None, name="call"):
        self.error = None
        self.gate_open_at_return = None
        self.done_at_return = None
        self.finished = threading.Event()

        def target():
            try:
                fn()
            except BaseException as exc:  # reported, never raised in the probe
                self.error = exc
            if sink is not None:
                self.gate_open_at_return = sink.gate.is_set()
                self.done_at_return = sink.done()
            self.finished.set()

        self.thread = probe_thread(target, name)

    def wait(self, timeout):
        return self.finished.wait(timeout)


def _describe(exc):
    return f"{type(exc).__name__}: {exc}"


def _close_quietly(spool, sink=None):
    if sink is not None:
        sink.gate.set()
    Call(spool.close, name="cleanup-close").wait(10)


def _same_events(got, expected):
    return collections.Counter(got) == collections.Counter(expected)


def _submit_settled(submit, sink):
    """Wait for a batch of submit() calls. If submit() itself waits on the held write (the design writes
    synchronously), release the write and go on: that breaks submit()'s contract, which the submit_async
    round reports, but it is not a flush()/close() race."""
    if submit.wait(5):
        return True
    sink.gate.set()
    return submit.wait(10)


def _held_last_write(EventSpool, op, batch_size, count, hold, tag):
    """Submit events, hold the write carrying the last one, call op(), and see whether it waits."""
    last = (tag, "last")
    sink = ProbeSink(hold_if=lambda events: last in events)
    spool = EventSpool(sink, batch_size=batch_size)
    events = [(tag, i) for i in range(count - 1)] + [last]
    submit = Call(lambda: [spool.submit(e) for e in events], name="submit")
    if not _submit_settled(submit, sink):
        _close_quietly(spool, sink)
        return "submit() did not return even after the held write was released"
    if submit.error:
        _close_quietly(spool, sink)
        return f"submit() raised {_describe(submit.error)}"
    sink.held.wait(3)  # the writer now holds the batch with the last event (unless it writes lazily)
    call = Call(getattr(spool, op), sink, name=op)
    call.wait(hold)
    sink.gate.set()
    if not call.wait(10):
        return f"{op}() had not returned 10 s after the held write was released"
    if op == "flush":
        _close_quietly(spool)
    if call.error:
        return f"{op}() raised {_describe(call.error)} while the sink was slow"
    if not call.gate_open_at_return:
        missing = len(events) - len(call.done_at_return)
        return (f"{op}() returned while the write holding the last event was still in progress "
                f"({missing} of {len(events)} events not yet written)")
    if not _same_events(call.done_at_return, events):
        return f"{op}() returned with {len(call.done_at_return)} of {len(events)} events written"
    if sink.overlap:
        return "the sink was written from two threads at once"
    return None


def round_flush_held(EventSpool):
    for batch_size, count in ((1, 5), (8, 30), (64, 200)):
        problem = _held_last_write(EventSpool, "flush", batch_size, count, FLUSH_HOLDS[0], f"f{batch_size}")
        if problem:
            return f"batch_size={batch_size}: {problem}"
    return None


def round_close_held(EventSpool):
    return _held_last_write(EventSpool, "close", 8, 30, FLUSH_HOLDS[0], "c8")


def round_repeated_flushes(EventSpool):
    """Several submit/flush cycles on one spool, each with its last write held."""
    current = {"last": None}
    sink = ProbeSink(hold_if=lambda events: current["last"] in events)
    spool = EventSpool(sink, batch_size=8)
    expected = []
    for cycle, hold in enumerate(FLUSH_HOLDS, 1):
        sink.gate.clear()
        sink.held.clear()
        last = ("cycle", cycle, "last")
        current["last"] = last
        events = [("cycle", cycle, i) for i in range(11)] + [last]
        expected += events
        submit = Call(lambda: [spool.submit(e) for e in events], name="submit")
        if not _submit_settled(submit, sink) or submit.error:
            _close_quietly(spool, sink)
            return f"cycle {cycle}: submit() failed or never returned"
        sink.held.wait(3)
        call = Call(spool.flush, sink, name="flush")
        call.wait(hold)
        sink.gate.set()
        if not call.wait(10):
            return f"cycle {cycle}: flush() had not returned 10 s after the held write was released"
        if call.error:
            _close_quietly(spool, sink)
            return f"cycle {cycle}: flush() raised {_describe(call.error)}"
        if not call.gate_open_at_return:
            _close_quietly(spool, sink)
            return (f"cycle {cycle}: flush() returned while the write holding the last event was still in "
                    f"progress (held {hold} s)")
        if not _same_events(call.done_at_return, expected):
            _close_quietly(spool, sink)
            return f"cycle {cycle}: flush() returned with {len(call.done_at_return)} of {len(expected)} events written"
    _close_quietly(spool, sink)
    return None


def round_paused_after_bookkeeping(EventSpool):
    """Pause the writer right after the queue's unfinished-task count reaches zero, then flush."""
    original = queue.Queue.task_done

    def task_done(self):
        original(self)
        t = threading.current_thread()
        if self.unfinished_tasks == 0 and t is not threading.main_thread() and not t.name.startswith("probe-"):
            _real_sleep(0.2)

    queue.Queue.task_done = task_done
    try:
        for batch_size in (1, 4):
            sink = ProbeSink()
            spool = EventSpool(sink, batch_size=batch_size)
            events = [("w", batch_size, i) for i in range(10)]
            for e in events:
                spool.submit(e)
            call = Call(spool.flush, sink, name="flush")
            if not call.wait(10):
                return f"batch_size={batch_size}: flush() did not return"
            _close_quietly(spool)
            if call.error:
                return f"batch_size={batch_size}: flush() raised {_describe(call.error)}"
            if not _same_events(call.done_at_return, events):
                return (f"batch_size={batch_size}: flush() returned with {len(call.done_at_return)} of "
                        f"{len(events)} events written while the writer paused after its queue bookkeeping")
    finally:
        queue.Queue.task_done = original
    return None


def round_parallel_producers(EventSpool, iterations=6, producers=8, per_producer=150):
    """Many producers, real per-write latency, a tiny switch interval; exactly-once, ordered, complete."""
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    rng = random.Random(7)
    try:
        for it in range(1, iterations + 1):
            sink = ProbeSink(latency=lambda: rng.uniform(0.001, 0.003))
            spool = EventSpool(sink, batch_size=16)
            expected = [(p, s) for p in range(producers) for s in range(per_producer)]

            def produce(p):
                for s in range(per_producer):
                    spool.submit((p, s))

            threads = [probe_thread(lambda p=p: produce(p), f"producer-{p}") for p in range(producers)]
            for t in threads:
                t.join(20)
            if any(t.is_alive() for t in threads):
                return f"iteration {it}: producers blocked in submit()"
            call = Call(spool.flush, sink, name="flush")
            if not call.wait(20):
                return f"iteration {it}: flush() did not return"
            _close_quietly(spool)
            if call.error:
                return f"iteration {it}: flush() raised {_describe(call.error)}"
            got = call.done_at_return
            if not _same_events(got, expected):
                dupes = len(got) - len(set(got))
                return (f"iteration {it}: after flush() {len(set(got))} of {len(expected)} events were written"
                        + (f", {dupes} duplicated" if dupes else ""))
            for p in range(producers):
                if [s for (q, s) in got if q == p] != list(range(per_producer)):
                    return f"iteration {it}: producer {p}'s events were written out of order"
            if sink.overlap:
                return f"iteration {it}: the sink was written from two threads at once"
    finally:
        sys.setswitchinterval(previous)
    return None


def round_background_delivery(EventSpool):
    """With no flush() or close(), submitted events must still reach the sink: the writer thread delivers
    them on its own. Two full batches, so a writer that waits for a full batch is not penalized."""
    sink = ProbeSink()
    spool = EventSpool(sink, batch_size=4)
    events = [("bg", i) for i in range(8)]
    submit = Call(lambda: [spool.submit(e) for e in events], name="submit")
    if not submit.wait(5):
        _close_quietly(spool, sink)
        return "submit() did not return"
    if submit.error:
        _close_quietly(spool, sink)
        return f"submit() raised {_describe(submit.error)}"
    deadline = time.monotonic() + 5
    while not _same_events(sink.done(), events) and time.monotonic() < deadline:
        _real_sleep(0.01)
    delivered = len(sink.done())
    _close_quietly(spool, sink)
    if delivered != len(events):
        return (f"{delivered} of {len(events)} submitted events reached the sink within 5 s without flush() "
                f"or close(): nothing writes them in the background")
    return None


def round_writes_from_writer_thread(EventSpool):
    """Across every round, sink.write() must never have run in a caller's thread (README: only the writer
    thread calls the sink)."""
    if CALLER_WRITES:
        seen = sorted(set(CALLER_WRITES))
        return (f"sink.write() ran in the caller's thread {len(CALLER_WRITES)} times, e.g. "
                + "; ".join(seen[:3]))
    return None


def round_idle_flush(EventSpool):
    sink = ProbeSink()
    spool = EventSpool(sink)
    if not Call(spool.flush, sink, name="flush").wait(5):
        return "flush() with nothing pending did not return"
    if not Call(spool.close, sink, name="close").wait(5):
        return "close() did not return"
    return None


def round_submit_async(EventSpool):
    """While the writer is inside a held write, submit() must still return."""
    sink = ProbeSink(hold_if=lambda events: True)
    spool = EventSpool(sink, batch_size=1)
    first = Call(lambda: spool.submit(("s", 0)), name="submit")
    if not first.wait(2):
        _close_quietly(spool, sink)
        return "submit() waited for the sink: it had not returned 2 s into the held write of its own event"
    sink.held.wait(3)  # the writer is now inside the held write (unless nothing writes in the background)
    more = Call(lambda: [spool.submit(("s", i)) for i in (1, 2)], name="submit")
    returned = more.wait(2)
    _close_quietly(spool, sink)
    if not returned:
        return "submit() waited for the sink: it had not returned 2 s into another event's held write"
    for call in (first, more):
        if call.error:
            return f"submit() raised {_describe(call.error)}"
    return None


def round_flush_after_close(EventSpool):
    sink = ProbeSink()
    spool = EventSpool(sink)
    spool.submit("x")
    if not Call(spool.close, sink, name="close").wait(5):
        return "close() did not return"
    call = Call(spool.flush, sink, name="flush")
    if not call.wait(3):
        return "flush() after close() did not return"
    return None


ROUNDS = [
    ("flush_waits_for_held_write", round_flush_held),
    ("close_waits_for_held_write", round_close_held),
    ("repeated_flushes", round_repeated_flushes),
    ("writer_paused_after_bookkeeping", round_paused_after_bookkeeping),
    ("parallel_producers", round_parallel_producers),
    ("idle_flush", round_idle_flush),
    ("background_delivery", round_background_delivery),
    ("submit_async", round_submit_async),
    ("flush_after_close", round_flush_after_close),
    ("writes_from_writer_thread", round_writes_from_writer_thread),  # last: reads what every round recorded
]


def main():
    try:
        from eventspool import EventSpool
    except BaseException as exc:
        for name, _ in ROUNDS:
            RESULTS[name] = f"cannot import eventspool.EventSpool: {_describe(exc)}"
        return
    for name, fn in ROUNDS:
        CURRENT_ROUND["name"] = name
        started = time.monotonic()
        try:
            problem = fn(EventSpool)
        except BaseException as exc:
            problem = f"probe error: {_describe(exc)}"
        RESULTS[name] = problem or "ok"
        RESULTS[name + "_s"] = round(time.monotonic() - started, 2)


if __name__ == "__main__":
    main()
    ok = all(v == "ok" for k, v in RESULTS.items() if not k.endswith("_s"))
    sys.stdout.write("PROBE_RESULT " + json.dumps(RESULTS, sort_keys=True) + "\n")
    sys.stdout.flush()
    os._exit(0 if ok else 1)
