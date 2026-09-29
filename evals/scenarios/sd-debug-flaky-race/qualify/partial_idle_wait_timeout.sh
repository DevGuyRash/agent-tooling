# Close to right but keeps a timing escape hatch: flush() waits for the writer to go idle after join(),
# bounded by a 0.1 s timeout "so a wedged sink cannot hang callers". A write slower than the timeout
# still lets flush() return early. The sleeps are removed and a slow-sink test reproduces the original
# failure, so only the stress check should fail.
set -e
git revert --no-commit $(git log --format=%H -n 2 -- eventspool/spool.py)
python3 - <<'PY'
from pathlib import Path
p = Path("eventspool/spool.py")
s = p.read_text()
repl = [
    ('''        self._closed = False
        self._writer = threading.Thread(''',
     '''        self._closed = False
        self._idle = threading.Event()  # set while the writer waits for events, cleared while it works
        self._writer = threading.Thread('''),
    ('''        self._queue.join()
''',
     '''        self._queue.join()
        # join() returns once the writer has taken the last event; wait for it to finish writing
        # (bounded, so a wedged sink cannot hang callers forever).
        self._idle.wait(timeout=0.1)
'''),
    ('''        batch = []
        item = self._queue.get()
''',
     '''        batch = []
        self._idle.set()
        item = self._queue.get()
        self._idle.clear()
'''),
]
for old, new in repl:
    assert s.count(old) == 1, old
    s = s.replace(old, new)
p.write_text(s)
t = Path("tests/test_spool.py")
s = t.read_text()
anchor = "    def test_parallel_producers(self):"
assert s.count(anchor) == 1
s = s.replace(anchor, '''    def test_flush_waits_for_a_slow_write(self):
        class SlowSink(MemorySink):
            def write(self, events):
                time.sleep(0.03)
                super().write(events)

        spool, sink = self.make_spool(SlowSink())
        spool.submit("a")
        spool.flush()
        self.assertEqual(sink.events, ["a"])

''' + anchor, 1)
t.write_text(s)
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
queue.join() returns as soon as the writer has taken the last event, not after it has been written, so flush() could return mid-write. That's the ~1-in-50 failure whenever the final write stalls. flush() now also waits for the writer to go idle, bounded at 100 ms so a wedged sink can't hang callers. I removed both sleeps and added test_flush_waits_for_a_slow_write, which fails on the old code.
EOF
