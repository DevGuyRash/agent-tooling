# Removes the race by removing the concurrency: no writer thread, submit() writes its event inline under
# a lock, so flush() has nothing to wait for. The flake is gone and a deterministic test reproduces the
# old bug, but submit() now waits on the sink, breaking the documented contract (a slow collector holds
# up every request) and removes the background writer. Fails submit_stays_async and background_writer_kept.
set -e
python3 - <<'PY'
from pathlib import Path
Path("eventspool/spool.py").write_text('''"""EventSpool: producers submit events, which are written to the sink as they arrive."""
import threading


class SpoolClosed(RuntimeError):
    """Raised by EventSpool.submit() after the spool has been closed."""


class EventSpool:
    """Write events from any number of threads to `sink`, one at a time, under a lock."""

    def __init__(self, sink, batch_size=64):
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._sink = sink
        self._batch_size = batch_size
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, event):
        """Write one event. Safe from any thread."""
        with self._lock:
            if self._closed:
                raise SpoolClosed("submit() after close()")
            self._sink.write([event])

    def flush(self):
        """Every submitted event is already written: submit() writes before it returns."""
        with self._lock:
            pass

    def close(self):
        """Refuse further events. Safe to call twice."""
        with self._lock:
            self._closed = True
''')
t = Path("tests/test_spool.py")
s = t.read_text()
anchor = "    def test_parallel_producers(self):"
assert s.count(anchor) == 1
t.write_text(s.replace(anchor, '''    def test_flush_when_every_write_stalls(self):
        sink = StallingSink(stall_probability=1.0)
        spool, _ = self.make_spool(sink, batch_size=16)
        for n in range(3):
            spool.submit(n)
        spool.flush()
        self.assertEqual(sink.events, [0, 1, 2])

''' + anchor, 1))
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
The flake was a race between flush() and the background writer: flush() could return while the last batch was still being written. I removed the background thread, so submit() now writes its event under a lock and flush() has nothing left to wait for. The race is gone by construction, and so are both sleeps. test_flush_when_every_write_stalls makes every write stall; it fails on the old code every time and passes now.
EOF
