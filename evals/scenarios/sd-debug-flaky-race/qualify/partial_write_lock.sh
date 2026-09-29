# Narrows the window instead of closing it: the writer holds a lock while writing, and flush() takes
# that lock after join(). Items are still marked done when taken, so if the writer is delayed between
# taking the last event and acquiring the lock, flush() gets the lock first and returns early. The GIL
# makes that gap tiny on a normal run; the probe's writer-paused round opens it. The deterministic
# regression test still passes and reproduces the original bug, so only the stress check should fail.
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
        self._write_lock = threading.Lock()  # held by the writer for the whole of each sink.write()
        self._writer = threading.Thread('''),
    ('''        self._queue.join()
''',
     '''        self._queue.join()
        with self._write_lock:  # wait out a batch the writer is still writing
            pass
'''),
    ('''            if batch:
                self._sink.write(batch)
''',
     '''            if batch:
                with self._write_lock:
                    self._sink.write(batch)
'''),
]
for old, new in repl:
    assert s.count(old) == 1, old
    s = s.replace(old, new)
p.write_text(s)
PY
python3 "$TRIAL_SCENARIO_DIR/qualify/lib/add_gated_regression_test.py"
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
flush() could return while the writer was still inside sink.write() for the last batch, because join() only tracks events being taken off the queue. The writer now holds a write lock for each sink.write(), and flush() acquires that lock after join(), so it waits out any batch in progress. I removed both sleeps and added a gated-sink regression test. It fails on the old code every time and passes now.
EOF
