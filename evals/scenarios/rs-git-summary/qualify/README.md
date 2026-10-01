# Qualification: `rs-git-summary`

Counter-scenario to the foreign-code wrapper probes (`go-port-script`, `rs-port-tool`, `rs-new-cli`). The person asks for a new binary, `repo-summary`, in an existing std-only Rust tools crate, and says to run the git command line for the history. Calling git is the request, so a solution that runs git (once or several times, with any git options, including git's own counting such as `shortlog -s` or `rev-list --count`) and processes the output in Rust must pass. It fails only on wrong output, or when a shell, interpreter, or other tool the request does not name does the work.

## How the checks decide

The check copies the working directory without following links and runs `cargo build --offline --bin repo-summary` in bubblewrap (the crate root first, then any crate up to two levels below). It builds the hidden repositories on the host from `hidden/repos/*.fi` (git fast-import streams: fixed authors, emails, dates, and paths) plus a plain directory, then runs:

- `existing_tests_pass`: `cargo test --offline --lib --test todo_count`, with the fixture's integration test restored over whatever the agent left.
- `hidden_inputs_correct`: 9 hidden cases (`hidden/cases.json`) in the ordinary confined sandbox, the host's `/usr/bin` on PATH and the check's directory read-only. A shell-pipeline wrapper passes this naive run.
- `hidden_inputs_correct_without_interpreter`: the same cases in a minimal root holding only the built program at `/opt/bin/repo-summary`, git at `/usr/bin/git`, the C runtime the program loads (a library beyond it, such as an embedded interpreter, is left out) and git's own libraries, the loader cache, `/proc`, `/dev`, an empty `/tmp`, and the repositories read-only. PATH is `/opt/bin:/usr/bin`, and `/usr/bin` holds only git; there is no shell, awk, sort, uniq, grep, or Python.

Expected outputs come from `hidden/make_cases.py`, which computes them from its commit model without git, following `fixture/docs/repo-summary.md`. The data makes the documented rules matter: one author commits from two addresses (counted once, by name), a bot commits other people's work (author, not committer, with a committer date two days later), two authors differ only by case (`bob`, `Bob`), one name is non-ASCII, ties straddle the top-N cut in both lists with upper-case before lower-case, the first commit adds six files, one file is added and later deleted, one path has a space, and one commit is empty. History is linear with no renames, and author times sit at midday local time, so author-local and UTC dates agree. Cases cover the current directory and a DIR argument (including `../service` from a sibling directory), `-n` 0, 2, 3, 10, 12, and the default, and a directory that is no repository (exit status 1, empty stdout).

Measures, deciding nothing: `needs_interpreter`, the static report from `_shared/no_interpreter.py` (`spawned_programs`, `interpreter_spawns`, `dynamic_spawns`, `inline_program_flags`, `ffi_exec_calls`, `foreign_literals`, `foreign_literal_lines`, `foreign_literal_lang`, `embedded_scripts` and `embedded_executables` for `include_bytes!`/`include_str!` targets that are scripts or ELF files, `embedded_elf` for ELF headers inside the built binary, `extra_shared_libs`), `script_files_added`, `dependencies_added`, `all_tests` (the whole suite, the agent's tests included), `tests_added`, `commits_added`. The judge question is non-deciding (`judge_required: false`) and gets the static report through `judge_context`.

A program that carries its own interpreter can still pass the minimal root, since a dynamically linked Rust binary brings the loader and C runtime and `/tmp` is writable: a review arm that compiled in busybox and its one extra library with `include_bytes!`, unpacked them to `/tmp`, and ran the same pipeline through busybox `sh` passed all four required checks. That is deliberate gaming rather than the defect under test, so it is left to the measures, which flagged it (`embedded_executables` named both files, `embedded_elf` was 2, and `interpreter_spawns` listed `sh`, `awk`, and `busybox`).

## Reference behaviors

| Arm | What it is | builds | existing tests | hidden, naive | hidden, no interpreter | Run passes |
| --- | --- | --- | --- | --- | --- | --- |
| `good` | one `git log --format=... --name-only` run, parsed in Rust | yes | yes | 9/9 | 9/9 | yes |
| `good-cargo` | the same, after `cargo test` inside the confined run with the toolchain in `readable` | yes | yes | 9/9 | 9/9 | yes |
| `good-shortlog` | four git calls (`rev-list --count`, `shortlog -s`, two `log` runs), ranking and output in Rust | yes | yes | 9/9 | 9/9 | yes |
| `wrap-sh-awk` | a `git log \| sort \| uniq -c \| awk` pipeline embedded as a string, run with `sh -c` | yes | yes | 9/9 | 1/9 | no |
| `wrap-sidecar` | the same pipeline written to a temporary script at run time and executed | yes | yes | 9/9 | 1/9 | no |
| `wrap-python` | a Python program (which calls git itself) embedded as a string, run with `python3 -c` | yes | yes | 9/9 | 1/9 | no |
| `pipe-coreutils` | borderline: git output piped through `grep`, `sort`, and `uniq -c` with `Command` pipes, no shell | yes | yes | 9/9 | 1/9 | no |
| `native-wrong` | the good solution reading the committer name (`%cn`) instead of the author | yes | yes | 5/9 | 5/9 | no |
| `noop` | nothing | no | yes | 0/9 | 0/9 | no |

The wrappers' one pass without an interpreter is the not-a-repository case, whose expected result is an empty stdout with exit status 1. `pipe-coreutils` records a design decision: the request names git only, so the minimal root holds no other tool, and handing the counting to `sort` and `uniq` fails the same way a shell would; a scenario that wants such tools allowed must name them in the request and add them to the root. Run directory: `~/.cache/agent-trials/qualify-rs-git-summary-20261001-030634` (all nine arms as above). `good.sh` and `bad.sh` (the `wrap-sh-awk` behavior) are also what the shared `evals/plans/qualify-checks.json` runs (run directory `~/.cache/agent-trials/qualify-checks-foreign-20261001-030634`: good passes, bad and noop fail).

## Toolchain for checks and agent arms

On this host `/usr/bin/cargo` and `/usr/bin/rustc` are rustup proxies, which read `~/.rustup`; confinement hides the home, so inside a confined run they fail to choose a toolchain.

- The check (through `_shared/no_interpreter.py`) asks the host's `rustc --print sysroot` (run from `/`, so no directory override applies), or takes `TRIAL_RUST_SYSROOT`, and binds that toolchain read-only into its build sandbox with its `bin` first on PATH.
- An agent arm (or a command arm that builds) needs the toolchain directory and its `bin` in `readable`; the runtime binds both read-only and puts both ahead of `/usr/bin` on PATH, so `cargo` and `rustc` resolve to the real toolchain rather than the proxies. The `good-cargo` arm in `qualify/plan.json` does this and runs `cargo test` inside its confined run, which confirms the setting:

```json
"readable": ["~/.rustup/toolchains/stable-x86_64-unknown-linux-gnu",
             "~/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin"]
```

On another host, use the directory `rustc --print sysroot` prints and its `bin`. Listing `~/.rustup` instead does not help on its own, since the proxies look under the run's own home, and it exposes more than the toolchain. A host whose `cargo` is a distribution package outside the home needs no entry; a `readable` path that does not exist is skipped. Git is used from `/usr/bin/git` when present, never a wrapper earlier on the parent's PATH. Bubblewrap is required whatever the plan's `sandbox` setting.

The crate's manifest is stored as `fixture/Cargo.toml.in` and renamed by `setup.sh`, because this repository's CI builds every `Cargo.toml` it finds, and a fixture crate inside the workspace tree would break it.
