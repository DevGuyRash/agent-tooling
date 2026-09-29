"""Shared by qualify scripts: a regression test that holds the write carrying the only event open on a
gate while flush() runs, so the ordering bug shows on every run instead of one in fifty."""
from pathlib import Path

p = Path("tests/test_spool.py")
s = p.read_text()
anchor_class = "class EventSpoolTests(unittest.TestCase):"
anchor_test = "    def test_parallel_producers(self):"
assert s.count(anchor_class) == 1 and s.count(anchor_test) == 1
s = s.replace(anchor_class, '''class GatedSink(MemorySink):
    """write() blocks until the test opens the gate, so a batch can be held in the middle of being written."""

    def __init__(self):
        super().__init__()
        self.writing = threading.Event()
        self.gate = threading.Event()

    def write(self, events):
        self.writing.set()
        if not self.gate.wait(timeout=10):
            raise AssertionError("gate never opened")
        super().write(events)


''' + anchor_class, 1)
s = s.replace(anchor_test, '''    def test_flush_waits_for_the_batch_being_written(self):
        # Regression: flush() used to return as soon as the writer had *taken* the last event off
        # the queue, before the sink had written it (test_parallel_producers failed when that last
        # write stalled). Hold the write open and check that flush() is still waiting.
        sink = GatedSink()
        spool, _ = self.make_spool(sink)
        self.addCleanup(sink.gate.set)
        spool.submit("only")
        self.assertTrue(sink.writing.wait(timeout=5))
        gate_open_when_flush_returned = []

        def flush():
            spool.flush()
            gate_open_when_flush_returned.append(sink.gate.is_set())

        flusher = threading.Thread(target=flush)
        flusher.start()
        flusher.join(timeout=0.3)
        self.assertTrue(flusher.is_alive(), "flush() returned while the batch was still being written")
        sink.gate.set()
        flusher.join(timeout=5)
        self.assertFalse(flusher.is_alive(), "flush() did not return after the write finished")
        self.assertEqual(gate_open_when_flush_returned, [True])
        self.assertEqual(sink.events, ["only"])

''' + anchor_test, 1)
p.write_text(s)
