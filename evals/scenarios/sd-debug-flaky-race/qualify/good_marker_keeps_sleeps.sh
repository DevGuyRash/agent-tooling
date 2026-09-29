# Another correct approach that leaves both speculative sleeps in place (they become inert): flush()
# queues a marker behind everything submitted so far and waits until the writer sets it after writing
# the batches ahead of it. Must pass: the sleeps are present but not load-bearing.
set -e
python3 - <<'PY'
from pathlib import Path
p = Path("eventspool/spool.py")
s = p.read_text()
old_flush = '''        self._queue.join()
        time.sleep(0.005)  # give the writer a moment to finish the batch it is writing
'''
new_flush = '''        if self._closed and not self._writer.is_alive():
            return
        marker = _FlushMarker()
        self._queue.put(marker)
        marker.wait()
        time.sleep(0.005)  # give the writer a moment to finish the batch it is writing
'''
old_stop = "_STOP = object()\n"
new_stop = '''_STOP = object()


class _FlushMarker(threading.Event):
    """Queued by flush(); the writer sets it once every event queued ahead of it has been written."""
'''
new_run = '''    def _run(self):
        while True:
            batch, markers, stop = self._take_batch()
            if batch:
                self._sink.write(batch)
            for marker in markers:
                marker.set()
            if stop:
                return

    def _take_batch(self):
        """Wait for the next item, then take whatever else is already queued, up to batch_size events.

        Flush markers taken along the way are returned so they can be set after the batch is written.
        """
        batch, markers = [], []
        item = self._queue.get()
        while True:
            if item is _STOP:
                return batch, markers, True
            if isinstance(item, _FlushMarker):
                markers.append(item)
            else:
                batch.append(item)
                if len(batch) >= self._batch_size:
                    return batch, markers, False
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return batch, markers, False
'''
assert s.count(old_flush) == 1 and s.count(old_stop) == 1
s = s.replace(old_flush, new_flush).replace(old_stop, new_stop, 1)
s = s[:s.index("    def _run(self):")] + new_run
p.write_text(s)
PY
python3 "$TRIAL_SCENARIO_DIR/qualify/lib/add_gated_regression_test.py"
python3 -m unittest -q >/dev/null 2>&1
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Root cause: flush() relied on queue.join(), but the writer called task_done() when it took each event, before writing it. flush() could therefore return while the final batch was still in sink.write(), and the test's stalling sink makes that visible about once in fifty runs.

flush() now puts a marker on the queue behind everything submitted so far and waits for the writer to set it, which the writer does only after writing the batches ahead of it. I left the two existing sleeps alone; they no longer matter for correctness. test_flush_waits_for_the_batch_being_written holds a write open and fails on the old code every time.
EOF
