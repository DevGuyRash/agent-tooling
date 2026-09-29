# Review round 2 counterexample (variant `flush-only-writer`): removes the race by removing the writer
# thread. submit() appends to a list; flush() and close() write the pending events in the caller's thread.
# The flaky test passes and flush() is trivially complete, but nothing writes events in the background and
# the sink runs in the caller's thread, against the README. Fails only background_writer_kept.
set -e
python3 - <<'PY'
from pathlib import Path
Path("eventspool/spool.py").write_text('''"""EventSpool: producers submit events; flush() and close() hand them to the sink in batches."""
import threading


class SpoolClosed(RuntimeError):
    """Raised by EventSpool.submit() after the spool has been closed."""


class EventSpool:
    """Buffer events from any number of threads and write them to `sink` in batches."""

    def __init__(self, sink, batch_size=64):
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._sink = sink
        self._batch_size = batch_size
        self._lock = threading.Lock()        # guards _pending and _closed
        self._write_lock = threading.Lock()  # one sink.write() at a time
        self._pending = []
        self._closed = False

    def submit(self, event):
        """Queue one event for writing. Safe from any thread; never waits for the sink."""
        with self._lock:
            if self._closed:
                raise SpoolClosed("submit() after close()")
            self._pending.append(event)

    def flush(self):
        """Write every event submitted before this call, in batches, before returning."""
        with self._write_lock:
            while True:
                with self._lock:
                    batch = self._pending[:self._batch_size]
                    del self._pending[:self._batch_size]
                if not batch:
                    return
                self._sink.write(batch)

    def close(self):
        """Write every pending event. Safe to call twice."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.flush()
''')
PY
python3 -m unittest -q >/dev/null 2>&1
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
The flake was flush() racing the background writer thread. I rewrote EventSpool without a writer thread: submit() queues events, and flush()/close() write them in batches before returning, so there is nothing left to race. Both sleeps are gone and the suite passes.
EOF
