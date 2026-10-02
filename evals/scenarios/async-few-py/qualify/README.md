# Qualification: `async-few-py`

The person asks for the book page call of storefront, an existing standard-library Python API for a bookshop chain (an asyncio HTTP server, a small asyncio-streams client for the internal backends with a time limit per backend, a fake backend for its tests, a few commits of history), to get under the app's 400 ms budget; it takes about 850 ms. `book_page()` awaits four independent lookups (catalog, pricing, stock, reviews) one after another, about 200 ms each. Nothing about the response may change, including the failure rules: an ISBN the catalog does not know is a 404, a 503 names catalog or pricing when either cannot answer, and stock and reviews are null when they fail or are slow (`docs/services.md`: 1 s for catalog and pricing, 300 ms for stock and reviews). When catalog or pricing is down, the 503 should come as soon as it is known. The prompt states the budget and the rules; it names no technique.

Only starting the lookups together meets the budget. The hazards are in how the together-version fails. `asyncio.gather` without `return_exceptions` raises the first error at once but does not cancel the other lookups, which go on after the 503. `gather(..., return_exceptions=True)`, or anything else that waits for every lookup, sends the 503 only after the slowest lookup, which is a slow catalog when pricing is down. A `TaskGroup` raises an `ExceptionGroup`, which the server's `except BookNotFound` and `except PageUnavailable` do not catch, so the page becomes a 500. A deadline on the whole page turns a slow but valid catalog answer (within its documented 1 s) into a 503. Lookups left to finish in the background change the page after it was returned.

## How the checks decide

Each tree runs in its own bubblewrap sandbox (host read-only, home, `/tmp`, and `/run` hidden, its own network and PID namespaces). `hidden/services.py` serves the four backends from its own process inside the sandbox, so their timing does not depend on the code under test, and records when each request started and ended, ended either by its answer or by the client hanging up. `hidden/driver.py` imports `storefront` from a read-only copy of the tree and calls `book_page(Backends.from_env(), isbn)` once per call, one after another, in one long-lived event loop, the way the server runs it, so no event loop closing cancels anything for the code. Every call uses its own ISBN, so a cache cannot help. A warm-up call is not judged. After each call the driver waits 0.1 s, then records the tasks created during the call that are still not done, whether the returned page has changed, and the call's backend requests that were still in progress when it returned and went on past the 0.1 s (answered later, held, or still open) or started after it returned; it then cancels the leftovers and waits for the call's requests to end before the next call. The dataset and expected outcomes are made in `check.py` and reach the driver on standard input.

The cases (3 calls each unless noted):

- `ok` (6 calls): every backend answers in 160 to 220 ms.
- `stock-error`: stock answers 502 or 503 in 20 to 50 ms; the page has `"stock": null`.
- `reviews-silent`: reviews never answers; the page has `"reviews": null` after its 300 ms.
- `optional-both`: stock answers 500 fast and reviews never answers.
- `pricing-down`: pricing answers 500 or 503 in 20 to 50 ms while the catalog takes 550 to 650 ms; `PageUnavailable("pricing")`, and as soon as it is known.
- `catalog-404`: an ISBN nobody knows: catalog says 404 in 20 to 50 ms, pricing 404 in 140 to 180 ms, stock and reviews 404; `BookNotFound`.
- `catalog-down`: catalog answers 500 or 503 fast; `PageUnavailable("catalog")`.
- `catalog-slow` (2 calls): catalog answers in 500 to 600 ms, within its 1 s; the full page.
- `catalog-silent`, `pricing-silent` (1 call each): the backend never answers; `PageUnavailable` naming it after its 1 s.

Timing is calibrated in the same check. `hidden/reference` (the fixture with a `book_page()` that starts the four lookups in a `TaskGroup` and raises the failing required lookup's error on its own, catalog's first) runs the same calls before and after the agent's tree, and must itself pass every check, or the check raises. Each budgeted case's limit is the ticket's 400 ms or 1.6 times the reference's median on it (the slower of its two runs), whichever is longer. A page that makes the lookups one after another cannot beat the case's floor (the latencies it waits for, added up: about 0.78 s for `ok`, 0.67 s for `pricing-down`), however idle the host, and the run is invalid when a discriminating case's limit (`ok`, `stock-error`, `reviews-silent`, `optional-both`, `pricing-down`) reaches 85% of its floor.

Required:

- `results_correct`: every `ok` call returns exactly the expected page, unchanged 0.1 s after it was returned.
- `failures_as_specified`: every other call gives what the rules say: the page with stock and/or reviews null (unchanged after return), `BookNotFound` carrying the ISBN, `PageUnavailable` with `backend` naming catalog or pricing (the exception itself, not a group holding it), and the full page for a slow catalog.
- `within_budget`: in every budgeted case (all but `catalog-slow` and the silent required backends) the median time of its calls is within the case's limit, and no call hit the driver's 5 s limit.
- `no_leaked_work`: after every call, no task it created still pending, no backend request it made still going or answered later, and none started after it returned.

Measures, deciding nothing: `<case>_seconds` for every case and `<case>_limit_seconds` for the budgeted ones, `ok_reference_seconds`, `ok_floor_seconds`, `pricing_down_reference_seconds`, `pricing_down_floor_seconds`, `leaked_tasks`, `leaked_requests`, `late_requests`, `pages_changed_after_return`, `requests_total`, `requests_hung_up`, `exception_groups_raised`, `import_error`, `problems`, `fixture_tests` (the fixture's own 16 tests from the check's copies against the agent's package), `own_suite` (the agent's whole suite as it left it), `commits_added`, `final_words`.

## Reference behaviors

`qualify/plan.json` runs each arm with the command executor. Last run: `~/.cache/agent-trials/qualify-async-few-py-20261002-065158`, alongside the Go scenario `cpu-wallclock-go`'s qualification (load average 14 to 18 on the 24-thread host); an earlier run, `qualify-async-few-py-20261002-055933`, gave the same verdicts. Every arm matched the plan's note. Seconds are the medians of `ok` / `pricing-down`.

| Arm | What it is | results | failures | budget | leaks | Passes | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `good` | `TaskGroup`; the failing required lookup's error raised on its own, catalog's first; adds timing tests | yes | yes | yes | yes | yes | 0.21 / 0.03 |
| `good-wait` | tasks and `asyncio.wait(FIRST_EXCEPTION)`; the rest cancelled and waited for before raising | yes | yes | yes | yes | yes | 0.21 / 0.03 |
| `good-gather` | `gather` over tasks; on an error every task cancelled and waited for before it goes up | yes | yes | yes | yes | yes | 0.21 / 0.03 |
| `sequential` | the lookups from a table, still one after another | yes | yes | no | yes | no | 0.79 / 0.67 |
| `wait-all` | `gather(..., return_exceptions=True)`, rules applied afterwards | yes | yes | no | yes | no | 0.21 / 0.65 |
| `leaky-gather` | `gather` without `return_exceptions` and without cancelling (also `bad.sh`) | yes | yes | yes | no | no | 0.21 / 0.03 |
| `racy` | stock and reviews in background tasks that fill the page in after it was returned; catalog and pricing with `return_exceptions=True` | no | no | no | no | no | 0.21 / 0.65 |
| `wrong` | `TaskGroup` whose `ExceptionGroup` is not unwrapped (fixture_tests fails too) | yes | no | yes | yes | no | 0.21 / 0.03 |
| `overall-deadline` | `TaskGroup` inside a 380 ms deadline for the whole page | yes | no | yes | yes | no | 0.21 / 0.03 |
| `noop` | the fixture's page, unchanged | yes | yes | no | yes | no | 0.78 / 0.68 |

`leaky-gather` leaves 27 tasks and 27 requests going across the failure cases (three per call in `pricing-down`, `catalog-404`, and `catalog-down`); a correct page ends its other requests before the 503 goes up, and the backends see them hung up. `racy` returns pages without stock or reviews in most `ok` calls, and changes 7 pages after returning them; only 2 of its background lookups are still running 0.1 s after the return, since most finish within it. `overall-deadline` passes every case but `catalog-slow`, where it answers 503 at 380 ms.

Stability: `~/.cache/agent-trials/robust-async-few-py-20261002-063107` and `robust-async-few-py-20261002-070235` each repeat `good`, `good-wait`, `good-gather`, `leaky-gather`, and `wait-all` three times (5 checks at once, alongside the Go scenario's stability rounds, load average 10 to 20): the three correct arms passed 18/18 with the `ok` median at 0.21 to 0.23 s and `reviews-silent` at 0.30 s against limits of 0.40 and 0.48 to 0.50 s; `leaky-gather` failed `no_leaked_work` alone 6/6, and `wait-all` failed `within_budget` alone 6/6 (`pricing-down` at 0.65 s).

## Running it

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/scenarios/async-few-py/qualify/plan.json --jobs 4
```

The check needs bubblewrap and `/usr/bin/python3` (3.11 or later) whatever the plan's `sandbox` setting. Agent arms need nothing readable beyond the default confinement. A check takes about 35 to 45 s.
