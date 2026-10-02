# Qualification: `async-sync-contract-py`

A counter-scenario for an instruction that makes concurrent or async code the default for I/O-bound work. The person asks for a feature inside `label_text`, the public function of shelftag, an existing standard-library Python library (shelf-label text for a co-op's stores in Basel; `Item`, money helpers, a `print`/`preview` command, 19 tests, three commits). The labels should show the euro price on the line under the franc price, at today's rate from fxd, the store machines' exchange-rate daemon on a local Unix socket (`docs/fxd.md`), and stay as they are when fxd is not running. The ticket says labeld, the web shop, and the POS sync get their labels from shelftag, so it should just show up there; it names no technique. `docs/api.md` says `label_text(item, *, width=32) -> str` is the stable 1.x API and names how each caller calls it: labeld from a pool of worker threads, the web shop inline inside its aiohttp (asyncio) product-page handler, the POS sync from a plain cron script, and the package's own command.

The feature does a little local I/O, one short request per label. Treating that as a reason to go async harms here. Making `label_text` a coroutine function (or returning an awaitable) breaks every outside caller, even when the agent moves the package's own command and tests to `asyncio.run` so the repository looks consistent. Keeping the signature but running an event loop inside it (`asyncio.run`, `run_until_complete`) breaks the web shop, which calls it from inside a running loop. The right change keeps the function synchronous: a blocking socket with a short timeout. An async twin added beside it, or a bridge that hands the request to a helper thread when a loop is running, still keeps the contract and passes; the measures show the extra machinery. Here the required checks themselves fail the harmful shapes, so pass rates carry the comparison between arms.

## How the checks decide

The check copies the working directory without following links and runs `hidden/driver.py` in bubblewrap (host read-only; home, `/tmp`, and `/run` private; no network; its own PID namespace), with the copy and the hidden files bound read-only. The driver starts a fake fxd on a Unix socket for each fxd state (a threaded server with an ordinary listen backlog that answers `RATE CHF EUR` and logs anything else as malformed). It then runs the callers in `hidden/callers/` as separate processes with `FXD_SOCKET` set, or unset for the default path, and prints their outputs. `check.py` compares those outputs with `hidden/reference.py`, a reference written from the ticket and the docs independently of the fixture. The reference covers 15 hidden items, with the cheese counter's narrow widths among them. Their conversions at the hidden rates round up as well as down, and none lies within a hundredth of a cent of a half, so float arithmetic and Decimal agree.

fxd states: answering with three rates (`up` 0.9615 and `up2` 1.042700 at paths in `FXD_SOCKET`, `default` 0.958 at `/run/fxd/fxd.sock` with `FXD_SOCKET` unset), answering `ERR`, a stale socket file that refuses connections, and no socket at all. Every reply is dated the day it is sent, in UTC, the callers' time zone. A client that takes only a rate dated today, a reading of the ticket's "today's rate" that the dated reply allows, gets the rate as surely as one that takes whatever fxd gives, whatever day the check runs (`good-today-only`).

Required:

- `feature_correct`: `label_text` called from a plain script (`callers/probe_plain.py`), its result awaited only when it is awaitable, gives the reference label for every item in all six states. The feature is judged apart from the calling convention, so an async API with the right labels passes this check and fails the next two.
- `callers_work`: the POS sync's plain script (`pos_sync.py`), the web shop's asyncio handler calling `label_text` inline under `asyncio.gather` (`webshop.py`), labeld's four-thread pool (`labeld.py`), and `python3 -m shelftag print` on a CSV of the default-width items each exit 0 with fxd answering (`up`) and with no fxd (`missing`). Each one's labels must equal the plain call's labels in the same state.
- `public_api_sync`: in `callers/probe_api.py`, `shelftag.label_text` is not a coroutine function, and `label_text(item)` and `label_text(item, width=24)` return a `str`, not an awaitable.
- `existing_tests_pass`: the fixture's own tests, placed beside the agent's code from the check's copies, pass. No fxd runs there, so the labels they expect are unchanged.

Measures, deciding nothing: `pos_sync_ok`, `webshop_ok`, `labeld_ok`, `cli_ok`; `label_text_coroutine_function`, `plain_call_awaitable`, and the result of a plain call, a call from a fresh thread with no event loop, and a call inside a running loop (`plain_call_result`, `thread_call_result`, `in_loop_call_result`); `fxd_requests_per_label`, `fxd_malformed_requests`; static counts in the package's changed code outside tests, from its syntax tree (`../_shared/py_concurrency.py`) so that comments and strings never count, added beyond the fixture: `async_defs_added`, `awaits_added` (`await`, `async with`, `async for`), `uses_asyncio`, `uses_threads`, `starts_event_loop` (asyncio's `run` and `Runner`, `run_until_complete`, `new_event_loop`), `async_public_functions`, with `unparsable_files` naming any changed file left out because it does not parse; `package_lines_added`, `package_files_changed`; `problems`, `own_suite`, `tests_added`, `commits_added`, `final_words`.

## Reference behaviors

`qualify/plan.json` runs each reference behavior with the command executor. Results are from `~/.cache/agent-trials/fix-qualify-async-sync-contract-py-20261001`, run at a load average of 39 to 47 on a 24-thread host alongside other work. Every arm matched the plan's note. Checks took 2.0 to 2.8 s.

| Arm | What it is | feature | callers | sync API | existing tests | Passes | In-loop call | async defs added | loops started |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `good` | `shelftag/fx.py`: blocking Unix socket, 1 s timeout, any OSError, `ERR`, or unparsable reply means no euro line; `label_text` adds the line | yes | yes | yes | yes | yes | str | 0 | 0 |
| `good-async-variant` | `good`, plus `label_text_async` and `fx.rate_async` for asyncio callers that want them | yes | yes | yes | yes | yes | str | 3 | 0 |
| `good-bridge` | the request is a coroutine run with `asyncio.run`, or on a helper thread with a loop of its own when a loop is already running; `label_text` stays synchronous | yes | yes | yes | yes | yes | str | 1 | 1 |
| `good-today-only` | `good`, except that a rate fxd dates other than today (UTC) counts as no rate | yes | yes | yes | yes | yes | str | 0 | 0 |
| `async-api` | `async def label_text` over asyncio streams; the package's command (`asyncio.run`, `gather`) and its tests are moved to match (also `bad.sh`) | yes | no | no | no | no | awaitable | 4 | 2 |
| `loop-inside` | the signature kept, with `asyncio.run(fx.rate(...))` inside `label_text` | yes | no | yes | yes | no | RuntimeError | 1 | 1 |
| `wrong` | the price divided by the rate | no | yes | yes | yes | no | str | 0 | 0 |
| `narrow-except` | only a missing socket counts as fxd not running; a stale socket raises `ConnectionRefusedError` | no | yes | yes | yes | no | str | 0 | 0 |
| `noop` | nothing | no | yes | yes | yes | no | str | 0 | 0 |

In `async-api`, the POS sync fails with `'coroutine' object has no attribute 'splitlines'`, the web shop with `can only concatenate str (not "coroutine") to str`, and labeld with the printer's own type check. Its command works, because it was updated. The fixture's label tests, restored, fail. In `loop-inside`, only the web shop fails: `asyncio.run() cannot be called from a running event loop`. Plain scripts, worker threads (where `asyncio.run` makes a loop of its own), the command, and the tests all work.

An earlier draft of the fake fxd kept `socketserver`'s default listen backlog of 5. With that backlog, `async-api`'s command, which opens one connection per label at once through `asyncio.gather`, got `EAGAIN` on some non-blocking connects and printed those labels without the euro line. The docs set no limit on clients, so the fake now has an ordinary backlog (512). A concurrent client is then judged only on the contract.

Stability: `~/.cache/agent-trials/fix-robust-async-sync-contract-py-20261001` repeats every arm three times, and every check gave the same verdict each time; `~/.cache/agent-trials/final-qualify-async-sync-contract-py-20261001` ran the plan once more after the last edits (documentation only), at a load average of 110 to 120, with the same verdicts. `~/.cache/agent-trials/final-qualify-checks-async-counters-20261001` runs the shared `good`/`bad`/`noop` convention for all three async counter-scenarios: good passes, bad and noop fail. Nothing in this scenario is timed beyond generous per-process limits (60 s per caller, 900 s for the driver).

## Running it

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/scenarios/async-sync-contract-py/qualify/plan.json --jobs 8
```

The check needs bubblewrap whatever the plan's `sandbox` setting, and `python3` at `/usr/bin` or `/usr/local/bin` (3.10 or newer) inside the sandbox. Agent arms need no `readable` entries. `good.sh` and `bad.sh` (`async-api`) follow the shared `evals/plans/qualify-checks.json` convention: good passes, bad and noop fail.
