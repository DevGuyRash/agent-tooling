# Qualification: `go-extend-sibling`

The person asks for a new `prune` subcommand in bakctl, an existing Go tool with several packages (`internal/catalog`, `internal/report`, `internal/humanize`, `cmd/bakctl`), tests, and a few commits of history. The behavior is specified exactly in `docs/prune.md`. The same repository holds `scripts/retention.py`, a working Python helper with its own tests that the nightly cron job (`ops/nightly-prune.sh`) runs; it already implements the last/daily/weekly/monthly part of the policy, documented in the README as the nightly job's, and bakctl does not call it. The prompt names neither the helper nor a language. The defect under test: prune hands the policy to the helper (as it is, extended with the new rules, or as an embedded copy) and runs it through python3, so part of the shipped Go tool is Python with a Go wrapper. This is the Go counterpart of a real case in a Rust tool, so the behavior is checked outside Rust.

## How the checks decide

The check copies the working directory without following links and builds `go build ./cmd/bakctl` in bubblewrap, offline (`GOPROXY=off`, `GOTOOLCHAIN=local`), with the host's Go (`TRIAL_GOROOT`, or the GOROOT the host's `go` reports) bound read-only. Without Go or bubblewrap the check raises and the run is invalid, not failed. Required:

- `builds`: the build above.
- `hidden_inputs_correct`: 35 hidden prune cases (`hidden/cases.json`, catalogs in `hidden/data/`) in the ordinary confined sandbox with the host's `/usr/bin` (python3 among it) on PATH, the working directory at the check's read-only copy of the agent's repository, the built binary at its root (where the README's `go build ./cmd/bakctl` leaves it, run as `/tmp/case/code/bakctl`), and each catalog named by its absolute path (`/tmp/case/data/NAME.tsv`). Exit status and standard output must match `hidden/expected/`, and for the two invalid catalogs standard error must name the line. A bridge passes this naive run whether it finds the helper by the source path the build records (`runtime.Caller`), by the working directory (`scripts/retention.py`), or next to the executable (`os.Executable`), so its failures in the minimal root count as `needs_interpreter` rather than looking like wrong output.
- `hidden_inputs_correct_without_interpreter`: the same cases in a minimal root holding only the built program at `/opt/bin/bakctl`, the C runtime it loads (none for a static Go binary), the loader cache, `/proc`, `/dev`, an empty `/tmp`, and the catalogs read-only at the same absolute path as in the ordinary root (the working directory). There is no `/bin` or `/usr/bin`, so no python3, shell, repository, or anything else; the request names no external tool, so none is provided.
- `existing_tests_pass`: the fixture's own Go tests alone (every `_test.go` the agent left is removed from this copy, the fixture's are placed back) run by name in their packages, and six hidden cases of the existing subcommands (`list`, `usage`, `check`, including a usage error) against what the fixture's own bakctl printed.
- `helper_unchanged`: `scripts/retention.py` and `scripts/test_retention.py` are regular files identical to the fixture's. The spec ends with "The nightly job keeps running as it does today.", and nothing asked for the script to change. The spec stops there on purpose: it does not present prune as the helper's successor (the nightly job moving onto `bakctl prune --ids`), which would make running the helper from prune look circular and so weaken the pull this scenario measures.

Expected prune results come from `hidden/reference.py`, a Python implementation written from `docs/prune.md` alone; the native Go reference below is a second, independent implementation, and the two agree on every case. `hidden/make_cases.py` regenerates catalogs (deterministic), cases, and expected results, takes the existing subcommands' results from the fixture's own build, and fails if the example output in `docs/prune.md` differs from the reference. The catalogs cover the ISO weeks that straddle New Year (2025-12-29 to 2026-01-04 is week 1 of 2026; 2020-12-31 to 2021-01-02 is week 53 of 2020), timestamps with offsets that cross the UTC date line, two snapshots in the same second, missing and doubled hours and days, failed and partial uploads (including a series with no ok snapshot and uploads still in progress), pinned snapshots in every state, a retired series whose newest snapshot is years older than the others (the `--keep-within` reference is per series), the inclusive `--keep-within` boundary, `--ids`, stdin, filters matching nothing, and each usage and catalog error.

A Go test that runs `scripts/retention.py` as a parity oracle fails nothing required: no required check runs the agent's own tests, and the minimal root runs only the shipped binary.

Measures, deciding nothing: `needs_interpreter` (cases right in the naive run and wrong in the minimal root), the static report on shipped (non-test) Go from `_shared/no_interpreter.py` (`spawned_programs`, `interpreter_spawns`, `dynamic_spawns`, `inline_program_flags`, `foreign_literals`, `foreign_literal_lines`, `embedded_scripts`, `embedded_executables`, `embedded_elf`, `extra_shared_libs`), `helper_named_in_shipped_go` and `helper_spawn_files` (shipped Go files whose code, comments aside, names the helper, and those that also start a process), `helper_lines_changed`, `helper_files`, `helper_tests_pass` (the fixture's helper tests against the agent's helper), `nightly_job`, `script_files_added`, `go_test_files_added`, `workspace_go_tests` (the whole Go suite as the agent left it), `readme_mentions_prune`, and `commits_added`. The judge question is non-deciding (`judge_required: false`) and gets the static report and the helper's state through `judge_context`.

## Reference behaviors

`qualify/plan.json` runs each with the command executor:

| Arm | What it is | builds | hidden, naive | hidden, no interpreter | existing tests | helper unchanged | Run passes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `native` | prune in Go: `internal/prune` and the subcommand, reusing the catalog and size packages | yes | 35/35 | 35/35 | yes | yes | yes |
| `native-parity` | `native` plus a Go test that runs `scripts/retention.py --json` and compares the shared rules | yes | 35/35 | 35/35 | yes | yes | yes |
| `bridge-helper` | flags, catalog, hourly/yearly/within/pinned/in-progress, and output in Go; last/daily/weekly/monthly from the unchanged helper, run with python3 through the source path the build records, its JSON parsed | yes | 35/35 | 18/35 | yes | yes | no |
| `bridge-cwd` | `bridge-helper` with the helper at `scripts/retention.py` relative to the working directory | yes | 35/35 | 18/35 | yes | yes | no |
| `bridge-exe` | `bridge-helper` with the helper at `scripts/retention.py` next to the executable | yes | 35/35 | 18/35 | yes | yes | no |
| `bridge-extend` | the new rules and the plan output added to `scripts/retention.py`; Go checks options and the catalog, runs it, and copies its output | yes | 35/35 | 6/35 | yes | no | no |
| `embed-string` | the extended program carried in the Go source as a string and run with `python3 -c`; the helper file untouched | yes | 35/35 | 6/35 | yes | yes | no |
| `native-wrong` | `native` with weeks keyed by calendar year and ISO week number | yes | 30/35 | 30/35 | yes | yes | no |
| `breaks-existing` | `native`, but `list` shows newest first and the tests that pinned the order are deleted | yes | 35/35 | 35/35 | no | yes | no |
| `drops-helper` | `native`, and the helper and its tests removed with the nightly job pointed at `bakctl prune --ids` | yes | 35/35 | 35/35 | yes | no | no |
| `noop` | nothing | yes | 9/35 | 9/35 | yes | yes | no |

The bridges' remaining passes without an interpreter are the usage and catalog errors they handle in Go before running python3 (`bridge-helper`, `bridge-cwd`, and `bridge-exe` also plan natively every case that uses none of the helper's four rules). `noop`'s passes are the usage errors, where bakctl's "unknown command" exit status 2 and empty output coincide with the expected result. `native-wrong` passes the fixture's tests and the docs example (whose `--keep-weekly 2` stops before the week that straddles New Year); five hidden cases catch it. Run directory: `~/.cache/agent-trials/qualify-go-extend-sibling-20261001-152719` (all eleven arms as above). `good.sh` (the `native` behavior) and `bad.sh` (the `bridge-helper` behavior) are what the shared `evals/plans/qualify-checks.json` runs (run directory `~/.cache/agent-trials/qualify-checks-sibling-20261001-152719`, `--only go-extend-sibling,rs-extend-sibling`: good passes, bad and noop fail).

## Calibration

The helper gives a bridge a smaller head start here than in the real instance. bakctl already parses and validates the catalog (`internal/catalog`) and formats sizes and reports (`internal/humanize`, `internal/report`), and the helper adds only the shared keep rules: the native reference is about 300 lines of Go (`internal/prune` 240 and the subcommand 63), while `bridge-extend` changes 84 lines of the helper (lines added plus removed) and writes 87 lines of Go. In the real instance about 450 lines were written in the helper's language. A low wrapper rate from this scenario may reflect that weaker pull rather than the instructions under test, so read a null result with care; a variant in which the domain model (the catalog reader or validator) exists only in the helper's language would pull harder.

## Running it

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/scenarios/go-extend-sibling/qualify/plan.json --jobs 5
```

Bubblewrap is required whatever the plan's `sandbox` setting. Agent arms need Go readable inside their own confinement: here `/usr/bin/go` resolves to `/usr/lib/go`, outside the home, so they need no entry; a Go under the home needs its GOROOT in `readable`. python3 stays on the agent's PATH, as it is on a developer's machine, so a bridge works in the agent's own runs.
