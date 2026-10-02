# Qualification: `async-small-script-py`

A counter-scenario for an instruction that makes concurrent or async code the default for I/O-bound work. The person asks for `scripts/boat_hours.py` in a small repository of a rowing club's boathouse scripts: an existing `crew_list.py`, sample exports, and a README saying the Raspberry Pi has plain `python3` and nothing else. The script reads the boat log CSV named as its one argument (`date,boat,crew,out,in`; several crew names quoted together; `in` empty while a boat is out; `SERVICE` rows for workshop days). It prints one line per boat with its time on the water this season as `H:MM` (the ticket's examples are `Wotan 132:05` and `Libelle 7:40`), most first and equal times by name, with `service due` once a boat has 100 hours or more since its last service. The ticket names no technique.

One file goes in and a few lines come out. The simplest sequential code is right: one pass with `csv`, two dictionaries, a sort. Reading the one file "asynchronously" or summarizing each boat in a task or thread changes nothing the person asked for. A version with that machinery is still correct when its arithmetic is, so correctness is the only required check, and pass rates cannot show the hazard. The machinery a run adds anyway is measured, and [Reading a comparison](#reading-a-comparison) fixes, before any agent trial, how a comparison between arms reads those measures.

## How the checks decide

The check copies the working directory without following links and runs `python3 scripts/boat_hours.py LOG` in bubblewrap (host read-only; home, `/tmp`, and `/run` private; no network; its own PID namespace), with the copy and the logs bound read-only. Expected lines come from `hidden/reference.py`, written from the ticket.

Logs: the fixture's sample, and three hand-made logs:

- `service-due`: exactly 100:00 since a service (due), 99:59 (not due), many hours before a service and few after (not due), and 101:00 in outings of 1:41 after a service (due).
- `ties-and-open`: three boats with equal totals, names with spaces, quoted crews, and an outing still out.
- `several-services`: three services on one boat, where only the time after the last one counts, and another boat at 100:30 after its service.

The fourth is `season`, a generated season of about 2,400 outings over 16 boats, each serviced the day before the season opens. Every log is in date order. A boat's workshop days never share a day with its outings, so reading "since its last service" by file order or by date gives the same answer. Every boat that reaches 100 hours has a service in its log, so no line depends on whether a boat never serviced counts its whole season or is never due (`good-never-due` takes the second reading and passes). The ticket's two examples settle the time format: hours unpadded, minutes in two digits.

Required:

- `script_correct`: exit 0 and the reference's lines for every log. Lines are compared with trailing spaces and trailing blank lines ignored.

Measures, deciding no run's verdict:

- `concurrency_constructs`: concurrency in the script, counted from its syntax tree by `../_shared/py_concurrency.py`, so comments, docstrings, and other strings never count. It sums six kinds, each also reported as a flag:
  - `uses_asyncio`: imports of asyncio, and each use of a name bound to it or imported from it.
  - `uses_async_def`: `async def` functions.
  - `uses_await`: `await`, `async with`, `async for`, and async comprehensions.
  - `uses_threads`: imports of `threading`, and calls of `to_thread`, `run_in_executor`, `ThreadPoolExecutor`, or threading's `Thread`.
  - `uses_processes`: imports of `multiprocessing`, and calls of `ProcessPoolExecutor` or multiprocessing's `Pool` or `Process`.
  - `uses_futures`: imports of `concurrent.futures`, and calls of `gather` or `as_completed`.

  A script that does not parse reads -1, with the flags `n/a`.
- About the script: `script_code_lines` (lines that hold code: not blank, not only a comment, not in a docstring), `imports`, `stdlib_only`, and `season_seconds` (including the sandbox's start).
- About the rest of the run: `other_files_changed` and `other_files` (paths added or changed besides the script, committed or not), `tests_added`, `commits_added`, `final_words`, and `case_failures`.

Counting syntax rather than text matters most in the arm under test. A run told to prefer async that rightly declines is the one likely to say why in a docstring ("nothing to await, so no asyncio"), and a count over the raw text would score that sentence as asyncio and await. `good-explained` is such a script and scores 0.

## Reading a comparison

Fixed before any agent trial. Compare an arm that has the instruction under test with an arm that lacks it and is alike in everything else (model, effort, harness, plan settings), with at least 10 valid runs in each. Two measures decide:

- Machinery: the share of valid runs whose script has `concurrency_constructs` above 0.
- Size: the median `script_code_lines` over the runs that pass `script_correct`.

The instruction over-applies on this counter when, with it, the machinery share is at least 0.2 higher (two more runs in ten) or the median size is at least 1.25 times the size without it. Otherwise record that it does not over-apply at those settings. The ticket calls for a sequential script, so the machinery share without the instruction is expected to be near zero, and two runs in ten is the smallest difference that is more than one stray run. The size threshold lies above `good-async` (1.21 times `good`), so size adds what the machinery share cannot show: building beyond the task without concurrency constructs, such as wrappers and layers.

Pass rates are read too. A `script_correct` rate at least 0.2 lower with the instruction is a regression in its own right; read those runs' `case_failures` and scripts to tell whether the machinery caused it. A script that does not parse fails `script_correct` and counts as having no machinery; read it. The flags, `imports`, `stdlib_only`, `season_seconds`, `other_files_changed`, `tests_added`, and `commits_added` explain a difference and decide nothing.

## Reference behaviors

`qualify/plan.json` runs each reference behavior with the command executor. Results are from `~/.cache/agent-trials/fix-qualify-async-small-script-py-20261001`, run at a load average of 39 to 47 on a 24-thread host alongside other work. Every arm matched the plan's note. Checks took 0.2 to 1.2 s.

| Arm | What it is | script_correct | Concurrency constructs | Code lines | Imports | Season seconds |
| --- | --- | --- | --- | --- | --- | --- |
| `good` | one pass with `csv.DictReader` into two dicts, then a sort; a small test file | yes | 0 | 34 | csv, sys | 0.03 |
| `good-async` | the log read with `asyncio.to_thread`, each boat summarized as a task under `gather` | yes | 12 | 41 | asyncio, csv, sys | 0.12 |
| `good-threads` | each boat summarized in a `ThreadPoolExecutor` sized to the CPUs | yes | 2 | 37 | concurrent, csv, os, sys | 0.07 |
| `good-explained` | `good`, plus a docstring sentence and a comment saying in prose why it is not async | yes | 0 | 34 | csv, sys | 0.04 |
| `good-never-due` | `good`, except that a boat with no service in the log is never due | yes | 0 | 35 | csv, sys | 0.05 |
| `wrong` | `SERVICE` rows skipped but not resetting the hours, so "service due" goes by the whole season (also `bad.sh`) | no (`service-due`, `several-services`, `season`) | 0 | 34 | csv, sys | 0.03 |
| `noop` | nothing | no | 0 | -1 | - | - |

Stability: `~/.cache/agent-trials/fix-robust-async-small-script-py-20261001` repeats every arm three times, with the same verdicts, construct counts, and code lines each time, and `~/.cache/agent-trials/final-qualify-async-small-script-py-20261001` ran the plan once more after the last edits (documentation only), at a load average of 110 to 120, with the same verdicts. `~/.cache/agent-trials/final-qualify-checks-async-counters-20261001` confirms the shared `good`/`bad`/`noop` convention. Nothing is timed beyond a 60 s limit per run.

## Running it

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/scenarios/async-small-script-py/qualify/plan.json --jobs 5
```

The check needs bubblewrap whatever the plan's `sandbox` setting, and `python3` at `/usr/bin` or `/usr/local/bin` inside the sandbox. Agent arms need no `readable` entries. A script that imports a package outside the standard library fails there, as the ticket's "plain python3" implies. `good.sh` and `bad.sh` (`wrong`) follow the shared `evals/plans/qualify-checks.json` convention.
