"""The canonical fix, shared by qualify scripts: queue items are marked done only after the sink has
written them, so flush()'s queue.join() waits for the write. Expects spool.py without its sleeps."""
from pathlib import Path

p = Path("eventspool/spool.py")
s = p.read_text()
assert "sleep" not in s, "take the sleeps out before applying the fix"
old_flush = '''        """Block until every event submitted before this call has been written by the sink."""
        self._queue.join()
'''
new_flush = '''        """Block until every event submitted before this call has been written by the sink.

        The writer marks each queued item done only after the sink has written it, so join()
        returning means everything queued so far has been written.
        """
        self._queue.join()
'''
new_run = '''    def _run(self):
        while True:
            batch, taken, stop = self._take_batch()
            try:
                if batch:
                    self._sink.write(batch)
            finally:
                # Done only now that the sink has the batch. Marking items done as they were taken
                # let flush() return while this batch was still being written.
                for _ in range(taken):
                    self._queue.task_done()
            if stop:
                return

    def _take_batch(self):
        """Wait for the next event, then take whatever else is already queued, up to batch_size.

        Returns the batch, how many queue items were taken, and whether the stop marker was taken.
        """
        batch = []
        taken = 0
        item = self._queue.get()
        while True:
            taken += 1
            if item is _STOP:
                return batch, taken, True
            batch.append(item)
            if len(batch) >= self._batch_size:
                return batch, taken, False
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return batch, taken, False
'''
assert s.count(old_flush) == 1 and s.count("    def _run(self):") == 1
s = s.replace(old_flush, new_flush)
s = s[:s.index("    def _run(self):")] + new_run
p.write_text(s)
