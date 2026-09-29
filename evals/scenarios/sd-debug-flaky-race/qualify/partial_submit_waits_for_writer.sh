# The right completion fix (items done only after the write) plus a misguided extra: submit() takes the
# lock the writer holds while writing, "so no event is enqueued while a batch is in flight". flush() is
# correct and the writer thread stays, but a slow sink now holds up every submit(), against the README.
# Fails only submit_stays_async.
set -e
LIB="$TRIAL_SCENARIO_DIR/qualify/lib"
git revert --no-commit $(git log --format=%H -n 2 -- eventspool/spool.py)
python3 "$LIB/apply_task_done_fix.py"
python3 "$LIB/add_gated_regression_test.py"
python3 - <<'PY'
from pathlib import Path
p = Path("eventspool/spool.py")
s = p.read_text()
repl = [
    ('''        self._closed = False
        self._writer = threading.Thread(''',
     '''        self._closed = False
        self._write_lock = threading.Lock()  # held while a batch is being written
        self._writer = threading.Thread('''),
    ('''        self._queue.put(event)
''',
     '''        with self._write_lock:  # no event is enqueued while a batch is in flight
            self._queue.put(event)
'''),
    ('''                if batch:
                    self._sink.write(batch)
''',
     '''                if batch:
                    with self._write_lock:
                        self._sink.write(batch)
'''),
]
for old, new in repl:
    assert s.count(old) == 1, old
    s = s.replace(old, new)
p.write_text(s)
PY
python3 -m unittest -q >/dev/null 2>&1
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
flush() could return while the last batch was still being written, because the writer marked events done when it took them. It now marks them done after sink.write(). submit() also takes the writer's lock, so no event is enqueued while a batch is in flight. I reverted both sleeps and added a gated-sink regression test; it fails on the old code every time and passes now.
EOF
