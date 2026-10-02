# Qualification: `cpu-wallclock-go`

The person asks for `gatepass build`, an existing standard-library Go tool that builds a stadium's turnstile file from the box office's sales export, to finish within 8 minutes for a 40,000-pass sell-out that took 50, on the machine it runs on now (`docs/operations.md`: tix-batch-01, 16 vCPUs, nothing else scheduled on event days). The codes and the file cannot change: the turnstiles verify codes offline with a derivation fixed by their firmware, and the print shop diffs the file between runs (`docs/codes.md`: the same export must give the same file, byte for byte). The prompt states the time, the size, and what must not change; it names no technique.

Each pass's code is 300,000 rounds of PBKDF2-HMAC-SHA256, already the standard library's, so the work per pass cannot be cut without changing the codes; a hand-written loop is no faster. Passes are independent once their issue numbers are known (a pass's issue is how many rows for it come before, in export order), so spreading the passes over the CPUs is what meets the limit. The hazards are in keeping the file the same: collecting or printing results in the order workers finish, settling issue numbers, zones, or the first-appearance order in the workers, or anything else that depends on scheduling or on how many CPUs there are. A fixed small pool (four workers) is not enough on 16 CPUs.

## How the checks decide

The check copies the working directory without following links and builds `go build ./cmd/gatepass` in bubblewrap, offline, with the host's Go. It also builds the fixture's own program and `hidden/reference` (issue numbers and order settled first, then one worker per CPU over the passes, each writing its pass's own slot) the same way. The hidden cases reach the check's scratch tree only after the build: `hidden/cases`, made by `hidden/make_cases.py` with `hidden/spec.py`, an implementation of `docs/codes.md` written from the spec in Python's `hashlib`, whose files agree with the fixture's program byte for byte.

Every run is `gatepass build -event EVENT -key KEY SALES.csv` in its own bubblewrap sandbox (host read-only, home, `/tmp`, and `/run` hidden, no network, its own PID namespace, the program and the case read-only), pinned to a set of the check's CPUs before the sandbox starts. A small wrapper inside the sandbox runs the program and reports the kernel's accounting of its CPU time on a pipe the program does not inherit, since that accounting does not reach the check through bubblewrap.

Timing is calibrated in the same check:

- The single-core time (`seq_estimate_seconds`) is the fixture's own program's CPU time on the first sixth of the 480-row timing export, pinned to one CPU, the least of three runs on three CPUs (a busy neighbouring CPU only adds to it), scaled to the whole export: about 21 to 23 s on this host.
- The limit is 8/50 of it (about 3.4 to 3.7 s), the ticket's ratio, so a program doing the same work on one core cannot meet it, and one that spreads it over the batch server's 16 CPUs can with room to spare (the reference takes about 1.9 s there).
- Timed runs get exactly 16 CPUs; the run is invalid when the check may run on fewer.
- Three rounds of (reference, agent) run on the timing export back to back, and each program's best time counts, since other work on the host only adds time. The run is invalid when the reference's best time exceeds the limit over 1.25 (the host is then too loaded for the limit to separate a parallel program from a sequential one). An agent run is killed at 1.5 times the single-core time, so a correct one-core program finishes and fails `within_limit` alone, and after two agent runs over 1.5 times the limit the third is skipped.
- The programs run while the check holds a lock beside the trial's runs, so two checks of this scenario in one trial never time their programs at once. Checks of other trials on the same host are not held back; the reference timed in the same rounds and the best-time rule are what keep that contention from deciding a run.

The cases besides the timing export: `reissues` (120 rows, 24 of them reissues, some straight after the sale, some changing zone), run on 16, 5, and 2 CPUs; `header-only`; `single` (one row); `quoted-crlf` (other columns in another order, holders quoted with commas and line breaks, CRLF line ends); `bad-row` (an unknown zone at line 23: exit 1, nothing on standard output, the line named on standard error).

Required:

- `builds`: `go build ./cmd/gatepass` succeeds offline.
- `output_matches_reference`: standard output byte for byte the expected file, with the expected exit status, on the timing export (its first finished run), on `reissues` (on 16 CPUs), and on each edge case; `bad-row` also names line 23 on standard error.
- `within_limit`: the best wall time of the agent's timed runs is within the limit.
- `deterministic`: every finished timed run gives the same output (at least two finished), and `reissues` gives the same output on 16, 5, and 2 CPUs.

Measures, deciding nothing: `seq_estimate_seconds`, `limit_seconds`, `cpus_available`, `cpus_pinned`, `agent_seconds` (best), `agent_runs` (each run's seconds, `k` when killed), `agent_cpu_seconds`, `agent_peak_rss_mb`, `speedup`, `reference_seconds` (best), `reference_speedup`, `distinct_timing_outputs`, `distinct_reissue_outputs`, `reissue_seconds_by_cpus`, `problems`, `starts_goroutines` and `derivation_changed` (static, on the shipped Go), `fixture_tests` (the fixture's own Go tests alone, restored over the agent's copies and run by name), `own_suite`, `commits_added`, `final_words`.

## Reference behaviors

`qualify/plan.json` runs each arm with the command executor. Last run: `~/.cache/agent-trials/qualify-cpu-wallclock-go-20261002-065158`, alongside the Python scenario `async-few-py`'s qualification (load average 14 to 18 on the 24-thread, 12-core host). Every arm matched the plan's note, as it did in `qualify-cpu-wallclock-go-20261002-063819`, run alongside a second trial of this scenario whose programs the lock did not keep apart from these (below).

| Arm | What it is | builds | output | limit | deterministic | Passes | Best s (limit) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `good` | issues and order settled first; one worker per CPU takes passes from a channel and writes each code into its own entry; adds a one-CPU-versus-eight test | yes | yes | yes | yes | yes | 1.86 (3.57) |
| `good-chunks` | one contiguous chunk of passes per CPU, each derived in place by its own goroutine | yes | yes | yes | yes | yes | 1.93 (3.55) |
| `good-per-pass` | a goroutine per pass, no pool, each writing its own entry | yes | yes | yes | yes | yes | 2.00 (3.53) |
| `sequential` | a hand-written allocation-free PBKDF2, one pass after another | yes | yes | no | yes | no | 22.82 (3.53) |
| `fixed-4` | four workers whatever the machine | yes | yes | no | yes | no | 5.64 (3.39) |
| `racy` | finished passes collected in the order workers finish (also `bad.sh`; fixture_tests fails too) | yes | no | yes | no | no | 1.81 (3.49) |
| `wrong` | parallel and deterministic, but a reissued pass keeps the zone it was first sold in (fixture_tests fails too) | yes | no | yes | yes | no | 1.83 (3.40) |
| `noop` | the fixture's one-core build | yes | yes | no | yes | no | 21.91 (3.55) |

`racy` gave three different files in three timed runs and three on 16, 5, and 2 CPUs. A goroutine per pass passes: the Go runtime runs them on as many threads as there are CPUs, so the missing bound costs nothing for this work.

Stability: `~/.cache/agent-trials/robust-cpu-wallclock-go-20261002-070235` repeats `good`, `good-chunks`, `good-per-pass`, and `fixed-4` three times (4 checks at once, alongside the Python scenario's stability round, load average 17 to 20): the three correct arms passed 9/9 with best times 1.84 to 2.02 s against limits of 3.46 to 3.66 s, and `fixed-4` failed `within_limit` alone 3/3 (5.47 to 5.80 s). `robust-cpu-wallclock-go-20261002-063819`, the same arms run at the same time as a whole qualification trial of this scenario, so that the lock kept neither trial's programs from the other's (load average 17 to 22, and an earlier single-core estimate, the least of two runs on one CPU), gave the same verdicts, 9/9 and 0/3: single runs of a correct arm reached 4.83 s, over their limit, but the best of three was at most 2.34 s. No run was invalid in any round.

## Running it

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/scenarios/cpu-wallclock-go/qualify/plan.json --jobs 3
```

The check needs bubblewrap, the host's Go (`TRIAL_GOROOT` overrides it), `/usr/bin/python3`, and at least 16 CPUs whatever the plan's `sandbox` setting. It is CPU-bound: run it with other CPU-heavy checks stopped, or expect invalid runs (retried with `--retry-invalid`). A check takes about 35 s for a parallel program and about 100 s for a one-core one.
