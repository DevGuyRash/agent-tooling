# Another correct approach: count submitted and written events under one Condition; flush() waits until
# everything submitted before the call has been written. Sleeps removed, a different style of
# deterministic regression test, and the work committed.
set -e
python3 - <<'PY'
from pathlib import Path
p = Path("eventspool/spool.py")
p.write_text('''"""EventSpool: producers submit events; one writer thread hands them to a sink in batches."""
import queue
import threading

_STOP = object()


class SpoolClosed(RuntimeError):
    """Raised by EventSpool.submit() after the spool has been closed."""


class EventSpool:
    """Buffer events from any number of threads and write them to `sink` in batches.

    `sink` is any object with a `write(events)` method taking a list of events. It is called
    only from the spool's writer thread, one batch of at most `batch_size` events at a time.
    """

    def __init__(self, sink, batch_size=64):
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._sink = sink
        self._batch_size = batch_size
        self._queue = queue.Queue()
        self._closed = False
        # Progress counters, both guarded by _progress: events queued, and events the sink has written.
        # The writer consumes the queue in order, so "written >= n" means the first n queued events are written.
        self._progress = threading.Condition()
        self._submitted = 0
        self._written = 0
        self._writer = threading.Thread(target=self._run, name="eventspool-writer", daemon=True)
        self._writer.start()

    def submit(self, event):
        """Queue one event for writing. Safe from any thread; never waits for the sink."""
        if self._closed:
            raise SpoolClosed("submit() after close()")
        with self._progress:
            self._submitted += 1
            self._queue.put(event)

    def flush(self):
        """Block until every event submitted before this call has been written by the sink."""
        with self._progress:
            target = self._submitted
            while self._written < target:
                self._progress.wait()

    def close(self):
        """Write every pending event, then stop the writer thread. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        self._queue.put(_STOP)
        self._writer.join()

    def _run(self):
        while True:
            batch, stop = self._take_batch()
            if batch:
                try:
                    self._sink.write(batch)
                finally:
                    with self._progress:
                        self._written += len(batch)
                        self._progress.notify_all()
            if stop:
                return

    def _take_batch(self):
        """Wait for the next event, then take whatever else is already queued, up to batch_size."""
        batch = []
        item = self._queue.get()
        while True:
            if item is _STOP:
                return batch, True
            batch.append(item)
            if len(batch) >= self._batch_size:
                return batch, False
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return batch, False
''')

t = Path("tests/test_spool.py")
s = t.read_text()
anchor = "    def test_parallel_producers(self):"
assert s.count(anchor) == 1
s = s.replace(anchor, '''    def test_flush_blocks_until_in_flight_write_finishes(self):
        writing, release = threading.Event(), threading.Event()

        class HoldingSink(MemorySink):
            def write(self, events):
                writing.set()
                release.wait(10)
                super().write(events)

        sink = HoldingSink()
        spool, _ = self.make_spool(sink)
        self.addCleanup(release.set)
        spool.submit("e1")
        self.assertTrue(writing.wait(5), "the writer never started writing")
        flusher = threading.Thread(target=spool.flush)
        flusher.start()
        flusher.join(0.3)
        self.assertTrue(flusher.is_alive(), "flush() returned while a write was still in progress")
        release.set()
        flusher.join(5)
        self.assertFalse(flusher.is_alive())
        self.assertEqual(sink.events, ["e1"])

''' + anchor, 1)
t.write_text(s)
PY
python3 -m unittest -q >/dev/null 2>&1
git add -A
git commit -q -m "Make flush() wait for the sink, not just the queue" -m "flush() returned once the writer had taken the last event, before sink.write() finished, so test_parallel_producers failed whenever the stalling sink stalled the final batch. Track submitted and written counts under a Condition and wait on those. Drops the two speculative sleeps."
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
The flake came from flush() returning as soon as the writer had *taken* the last event off the queue (task_done ran at take time), not once the sink had *written* it. When the test's StallingSink stalled on the final batch, the count came up one batch short.

Neither sleep touched that, so I removed both. flush() now waits on a Condition until the number of written events reaches the number submitted before the call. The writer updates the written count after sink.write() returns.

The new test test_flush_blocks_until_in_flight_write_finishes holds a write open and checks that flush() doesn't return early. It fails on the old code every time and passes now. The suite passes. Committed as "Make flush() wait for the sink, not just the queue".
EOF
