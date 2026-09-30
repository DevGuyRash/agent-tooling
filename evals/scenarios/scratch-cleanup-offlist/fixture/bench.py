"""Benchmark the two dedupe implementations against the sample feed."""
import json
import time
from pathlib import Path

import dedupe_hashset
import dedupe_scan

DATA = Path(__file__).parent / "data" / "events_sample.jsonl"


def load():
    with open(DATA) as f:
        return [json.loads(line) for line in f]


def timeit(fn, records, repeats=3):
    best = None
    for _ in range(repeats):
        start = time.perf_counter()
        fn(records)
        elapsed = time.perf_counter() - start
        best = elapsed if best is None else min(best, elapsed)
    return best


def main():
    records = load()
    scan_time = timeit(dedupe_scan.dedupe, records)
    hashset_time = timeit(dedupe_hashset.dedupe, records)
    print(f"records: {len(records)}")
    print(f"dedupe_scan:    {scan_time * 1000:.2f} ms")
    print(f"dedupe_hashset: {hashset_time * 1000:.2f} ms")


if __name__ == "__main__":
    main()
