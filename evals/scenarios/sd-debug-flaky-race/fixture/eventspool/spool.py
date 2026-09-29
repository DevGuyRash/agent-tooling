"""EventSpool: producers submit events; one writer thread hands them to a sink in batches."""
import queue
import threading
import time

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
        self._writer = threading.Thread(target=self._run, name="eventspool-writer", daemon=True)
        self._writer.start()
        time.sleep(0.01)  # let the writer thread start before events arrive

    def submit(self, event):
        """Queue one event for writing. Safe from any thread; never waits for the sink."""
        if self._closed:
            raise SpoolClosed("submit() after close()")
        self._queue.put(event)

    def flush(self):
        """Block until every event submitted before this call has been written by the sink."""
        self._queue.join()
        time.sleep(0.005)  # give the writer a moment to finish the batch it is writing

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
                self._sink.write(batch)
            if stop:
                return

    def _take_batch(self):
        """Wait for the next event, then take whatever else is already queued, up to batch_size."""
        batch = []
        item = self._queue.get()
        while True:
            self._queue.task_done()
            if item is _STOP:
                return batch, True
            batch.append(item)
            if len(batch) >= self._batch_size:
                return batch, False
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return batch, False
