import random
import threading
import time
import unittest

from eventspool import EventSpool, MemorySink, SpoolClosed

PRODUCERS = 8
EVENTS_PER_PRODUCER = 200


class StallingSink(MemorySink):
    """Stands in for the audit collector: most writes are instant, but now and then one stalls."""

    def __init__(self, stall_probability=0.02, stall_seconds=0.02):
        super().__init__()
        self.stall_probability = stall_probability
        self.stall_seconds = stall_seconds

    def write(self, events):
        if random.random() < self.stall_probability:
            time.sleep(self.stall_seconds)
        super().write(events)


class EventSpoolTests(unittest.TestCase):
    def make_spool(self, sink=None, **kwargs):
        sink = MemorySink() if sink is None else sink
        spool = EventSpool(sink, **kwargs)
        self.addCleanup(spool.close)
        return spool, sink

    def test_flush_writes_submitted_events(self):
        spool, sink = self.make_spool()
        spool.submit({"n": 1})
        spool.submit({"n": 2})
        spool.flush()
        self.assertEqual(sink.events, [{"n": 1}, {"n": 2}])

    def test_events_keep_submission_order(self):
        spool, sink = self.make_spool(batch_size=7)
        for n in range(100):
            spool.submit(n)
        spool.flush()
        self.assertEqual(sink.events, list(range(100)))

    def test_batches_never_exceed_batch_size(self):
        spool, sink = self.make_spool(batch_size=5)
        for n in range(53):
            spool.submit(n)
        spool.flush()
        self.assertTrue(sink.batches)
        self.assertLessEqual(max(len(batch) for batch in sink.batches), 5)

    def test_flush_with_nothing_pending_returns(self):
        spool, sink = self.make_spool()
        spool.flush()
        self.assertEqual(sink.events, [])

    def test_close_writes_pending_events(self):
        sink = MemorySink()
        spool = EventSpool(sink)
        for n in range(10):
            spool.submit(n)
        spool.close()
        self.assertEqual(sink.events, list(range(10)))

    def test_submit_after_close_raises(self):
        spool, _ = self.make_spool()
        spool.close()
        with self.assertRaises(SpoolClosed):
            spool.submit("late")

    def test_close_twice_is_harmless(self):
        spool, _ = self.make_spool()
        spool.close()
        spool.close()

    def test_rejects_batch_size_below_one(self):
        with self.assertRaises(ValueError):
            EventSpool(MemorySink(), batch_size=0)

    def test_parallel_producers(self):
        sink = StallingSink()
        spool, _ = self.make_spool(sink, batch_size=16)

        def produce(producer):
            for seq in range(EVENTS_PER_PRODUCER):
                spool.submit({"producer": producer, "seq": seq})

        threads = [threading.Thread(target=produce, args=(p,)) for p in range(PRODUCERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        spool.flush()

        events = sink.events
        self.assertEqual(len(events), PRODUCERS * EVENTS_PER_PRODUCER)
        for p in range(PRODUCERS):
            seqs = [e["seq"] for e in events if e["producer"] == p]
            self.assertEqual(seqs, list(range(EVENTS_PER_PRODUCER)))


if __name__ == "__main__":
    unittest.main()
