# eventspool

Buffered, batched writing of audit events from multi-threaded services. Request handlers call `submit()`; one writer thread hands the events to a sink in batches, so a slow sink never holds up a request.

```python
from eventspool import EventSpool, JsonlSink

spool = EventSpool(JsonlSink("audit.jsonl"), batch_size=64)
spool.submit({"user": "ana", "action": "login"})
...
spool.flush()   # every event submitted so far is now in audit.jsonl
spool.close()   # flush, then stop the writer thread
```

## Guarantees

- `submit()` is safe to call from any thread and never waits for the sink.
- The sink's `write(events)` is called only from the writer thread, one batch at a time, with each producer's events in the order it submitted them.
- `flush()` returns once every event submitted before the call has been written by the sink.
- `close()` writes every pending event and stops the writer thread; `submit()` afterwards raises `SpoolClosed`.

A sink is any object with a `write(events)` method that takes a list of events. `MemorySink` keeps them in memory (for tests); `JsonlSink` appends one JSON line per event to a file.

## Development

Standard library only (Python 3.11+). Run the tests with `python3 -m unittest`.
