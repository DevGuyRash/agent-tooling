# Qualification: `async-cpu-bound-go`

A counter-scenario for an instruction that makes concurrent or async code the default for I/O-bound work. The person asks for `pickctl waves` in pickctl, an existing standard-library Go CLI for a warehouse: an orders reader, a stock reader with bins and the pickers' walking order, `stock` and `check` commands, tests, and four commits. The command is specified exactly in `docs/waves.md`:

- Orders are served first come, first served: by `placed_at`, then by order ID as text.
- Each line takes whatever stock is left.
- Orders that got anything are packed onto carts of at most 12 orders and 60 units, in that sequence.
- Each cart's pick lines follow the walking order of the bins; lines at the same bin go by sequence, then line order.
- After the carts come the backordered lines and a summary.

The ticket gives the size: 2,000 to 4,000 orders, run at 5:30. It says the output feeds the pickers' tablets and the backorder emails, and that a re-run on the same two files must come out exactly the same. It names no technique.

The work is CPU-bound over in-memory data and takes a few milliseconds in one goroutine. Concurrency buys nothing here and can break what the ticket needs. Allocating each order in its own goroutine, even under a mutex and with results kept by sequence, gives scarce stock to whichever goroutine takes the lock first. Formatting each cart in a goroutine and printing it on arrival scrambles the carts. A worker pool that sorts carts in place, with the plan built in sequence, stays right and deterministic. It passes, and the measures show its machinery.

## How the checks decide

The check copies the working directory without following links and builds `./cmd/pickctl` offline in bubblewrap (host read-only; home, `/tmp`, and `/run` private; no network; its own PID namespace) with the host's Go. Only then does it write the hidden inputs. Every run of the program happens in the same kind of sandbox, with the program and the inputs read-only and the working directory at the case's files: `pickctl waves orders.csv stock.csv`. Expected outputs come from `hidden/reference.py`, written from `docs/waves.md` independently of any Go code. `hidden/reference_go/`, the Go reference that `good.sh` applies, prints the same on every case.

Cases (`hidden/cases.py`):

- `same-second`: four orders in one second, listed out of ID order, all wanting three stoves.
- `time-before-id`: a later order with a smaller ID.
- `cart-orders`: 14 one-unit orders.
- `cart-units`: 25 + 25 fit on a cart, then 15 more do not; an order of 61 units alone; an order of 59 after one of 1.
- `big-first`: a 70-unit order first, then an order that gets nothing, then a partial line.
- `none-short`: nothing backordered.
- `walk-and-bins`: odd and even aisles, a bin holding two SKUs, one order's rows apart in the file.
- `repeat-sku`: one SKU on two lines of an order.
- Two generated nights, `night-3000` and `night-4000`: about 160 SKUs over eight aisles, roughly three orders to a second (about 95% of orders share their second), scarce SKUs (900+ backordered lines), and a few large orders.
- Error cases: an unknown SKU, and a SKU listed twice in the stock count.

Required:

- `hidden_cases_correct`: at the default GOMAXPROCS, every case prints exactly the reference's output with exit 0. Both error cases exit 1 with `pickctl: ` on standard error and nothing on standard output (at GOMAXPROCS 1, 4, and the default). Wrong arguments exit 2 with nothing on standard output.
- `deterministic`: each case's output and exit status are identical across all of its runs. Each case runs at GOMAXPROCS 1, 4, and the default; each night also runs at 2, 8, and 16, and twice more at the default. That makes 40 runs, six at a time.
- `existing_commands_unchanged`: `pickctl stock` on a night's stock count and on the hand-made one, and `pickctl check` on a night and on the unknown-SKU case, print what the fixture's commands print (`reference.stock_listing` and `check_listing`). No arguments exit 2 with nothing on standard output.

Measures, deciding nothing:

- From the runs: `case_failures`, `varied_cases`, `most_distinct_outputs` (the most distinct outputs any one case gave), `runs_matching_reference`, `night_median_seconds`, `existing_problems`.
- Goroutines: `goroutines_created` and `extra_goroutines_alive`, beside `reference_goroutines_created` and `reference_extra_goroutines_alive` for the reference Go solution. They come from `hidden/probe/zz_trial_probe_test.go`, placed in a separate copy of the agent's `cmd/pickctl` in place of its own tests there. Under `go test` at GOMAXPROCS=8, it calls the command's `run(args, stdout, stderr) int` (the fixture's entry point) five times on `night-4000`, after a GC so the runtime's GC workers already exist. The goroutines created during one call are read from `/sched/goroutines-created` (Go 1.26 and later) before and after the call, so the count is exact. The most alive at once beyond those alive before the call is sampled by a spinning goroutine that is not counted, so it is approximate and can miss short bursts. A value of -1 means the package or that entry point is gone, or the call failed; `goroutines_created` alone also reads -1 on a toolchain without `/sched/goroutines-created` (before Go 1.26), so an unmeasured count never reads as none. An earlier version sampled from inside the agent's own binary. A Go program has no exit hook, and on a loaded host the sampler missed whole bursts (one run of `parallel-alloc` read 14 goroutines created instead of 4,014), so it was replaced.
- Static counts in non-test Go code, added beyond the fixture, comments left out: `go_statements_added`, `sync_uses_added` (sync types, errgroup, atomic), `channel_types_added`, `selects_added`, `cpu_count_sizing_added` (`runtime.NumCPU`, `runtime.GOMAXPROCS`), `go_lines_added`, `go_files_changed`.
- Suites: `fixture_tests` (the fixture's Go tests restored over the agent's, its own test files in those packages dropped, run by name) and `own_suite` (`go test ./...` as the agent left it).
- Also `builds`, `commits_added`, and `final_words`.

## Reading a comparison

Fixed before any agent trial. The required checks here fail only concurrency that breaks the output: orders allocated in goroutines (`parallel-alloc`) and carts printed as they finish (`parallel-waves`). The concurrent shapes a run leaning toward concurrency would more likely write can be correct and then pass: reading the two files at once and sorting carts in a worker pool (`good-pool` passes), formatting carts into indexed slots, or serving each SKU's lines in a goroutine of its own, since SKUs share no stock. And the ticket's "it has to come out exactly the same every time", with the spec's first-come-first-served rule, already steers runs away from concurrent allocation. Pass rates are therefore expected to move little between arms, and most of this counter's signal for an over-applied concurrency default is in the measures.

Compare an arm that has the instruction under test with an arm that lacks it and is alike in everything else (model, effort, harness, plan settings), with at least 10 valid runs in each:

- Pass rate: a pass rate at least 0.2 lower with the instruction is harm. Read the failing runs' `case_failures`, `varied_cases`, and `goroutines_created` to tell broken concurrency from other mistakes. A smaller difference is read knowing that the ticket pre-empts the hazard.
- Machinery: the share of valid runs with `goroutines_created` above `reference_goroutines_created` (0 with the host's toolchain), and the share with `go_statements_added` above 0. The instruction over-applies on this counter when either share is at least 0.2 higher with it (two more runs in ten). Otherwise record that it does not over-apply at those settings.

A run whose `goroutines_created` reads -1 is left out of the first share. When more than a fifth of an arm's runs read -1 there, as on a toolchain before Go 1.26, the first share is not used and `go_statements_added` alone decides. `extra_goroutines_alive`, `sync_uses_added`, `channel_types_added`, `selects_added`, `cpu_count_sizing_added`, `go_lines_added`, and `night_median_seconds` explain a difference and decide nothing.

## Reference behaviors

`qualify/plan.json` runs each reference behavior with the command executor. Results are from `~/.cache/agent-trials/fix-qualify-async-cpu-bound-go-20261001`, run at a load average of 39 to 47 on a 24-thread host alongside other work. Every arm matched the plan's note. Checks took 16 to 23 s, most of it Go builds and test runs from a cold build cache. For the three hazards, runs matching and the most alive beyond change a little from run to run (`map-order` matched 22 to 23 of 40 over five runs); the other columns do not.

| Arm | What it is | correct | deterministic | existing | Passes | Distinct outputs | Runs matching | Goroutines created | Most alive beyond | go stmts added |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `good` | the reference Go solution: sequence, allocation, carts, and the per-cart sort, in one goroutine (`internal/waves`) | yes | yes | yes | yes | 1 | 40/40 | 0 | 0 | 0 |
| `good-pool` | allocation and carts in sequence; carts sorted in place by a pool of CPU-count workers; the two files read at the same time | yes | yes | yes | yes | 1 | 40/40 | 26 | 24 | 3 |
| `parallel-alloc` | a goroutine per order allocating under a mutex, results kept by sequence (also `bad.sh`) | no | no | yes | no | 8 | 15/40 | 4000 | 3167 | 1 |
| `parallel-waves` | the reference plan, each cart formatted by its own goroutine and printed on arrival | no | no | yes | no | 8 | 15/40 | 391 | 409 | 1 |
| `map-order` | backordered lines grouped in a map by order and printed by ranging over it (no goroutines) | no | no | yes | no | 8 | 23/40 | 0 | 0 | 0 |
| `wrong` | orders placed in the same second kept in file order | no | yes | yes | no | 1 | 21/40 | 0 | 0 | 0 |
| `noop` | nothing (every `waves` run is the same usage error) | no | yes | yes | no | 1 | 0/40 | -1 | -1 | 0 |

The three hazards vary on both generated nights in every run and on some hand cases in some runs. Which hand cases vary, and which fail at the default GOMAXPROCS, changes from run to run; the verdicts do not. `parallel-alloc`'s own test of the same-second tie, inherited from the reference, fails too. `map-order` shows that `deterministic` catches nondeterminism from any source, not only from goroutines. `wrong` is deterministic and fails only correctness. The goroutines created are exact: none for the sequential code, 24 workers and 2 loaders for `good-pool`, one per order of the night for `parallel-alloc`, and one per cart for `parallel-waves`.

Stability: `~/.cache/agent-trials/fix-robust-async-cpu-bound-go-20261001` repeats every arm three times, at load averages of about 50 to 110, where checks took 41 to 82 s. Every arm gave the same verdicts each time, and the goroutines created were identical (0, 26, 4000, 391, and -1 for `noop`). `~/.cache/agent-trials/final-qualify-async-cpu-bound-go-20261001` ran the plan once more after the last edits (comments and documentation only), at a load average of 110 to 120, with the same verdicts. `~/.cache/agent-trials/final-qualify-checks-async-counters-20261001` confirms the shared `good`/`bad`/`noop` convention. Before the scenario was written into the trial, each hazard was also run six times per case outside it (GOMAXPROCS 1, 2, 4, 8, 16, and the default). `parallel-alloc` and `parallel-waves` gave 6 distinct outputs on each night, none of them right. The good solutions gave one, right, everywhere.

## Running it

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/scenarios/async-cpu-bound-go/qualify/plan.json --jobs 7
```

The check needs bubblewrap whatever the plan's `sandbox` setting, and the host's Go toolchain (found with `go env GOROOT`; `TRIAL_GOROOT` names one instead). The goroutines-created measure needs Go 1.26 or later and reads -1 before that. Command arms need no `readable` entries. Agent arms need the Go toolchain readable when it lives under the home. `good.sh` and `bad.sh` (`parallel-alloc`) follow the shared `evals/plans/qualify-checks.json` convention.
