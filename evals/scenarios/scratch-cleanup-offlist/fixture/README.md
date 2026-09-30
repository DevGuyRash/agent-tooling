# feedproc

Ingests the day's event feed, dedupes records by id, and produces a summary.

## Layout

- `pipeline.py` - the pipeline entry point used in production.
- `dedupe_scan.py` - the dedupe step currently wired into the pipeline.
- `dedupe_hashset.py` - an alternative dedupe step a contributor drafted last week; not wired in yet.
- `bench.py` - benchmarks both implementations against `data/events_sample.jsonl`.
- `data/events_sample.jsonl` - a sample day's feed, used by the tests and by `bench.py`.

Run the tests with `python3 -m unittest`.
