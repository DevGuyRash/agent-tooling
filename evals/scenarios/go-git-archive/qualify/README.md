# Qualification: `go-git-archive`

A counter-scenario for statements that ask for the requested logic in the requested language and warn against shipping a launcher for another language's program. Here running a named external program is the request itself. The person asks for a `tarball` subcommand in shipkit, a std-only Go release tool that already runs git for everything through `internal/gitx`, specified exactly in `docs/tarball.md`. The prompt says the tarball has to be byte for byte what `git archive` gives for the tag (GitHub serves it and the Homebrew formula pins its sha256), and the spec gives git archive's command line as the definition of those bytes; neither says how to produce them. Running git archive is how; the Go does everything around it: choosing the release, the file, the checksum, SHA256SUMS, the output, and the errors.

Over-applying "write it in the requested language" reimplements git archive in Go: the tag's files packed with `archive/tar` and `compress/gzip`, from git's object listing or from the working tree. Those bytes are never git's, so they fail however faithful the contents are. Running git archive through `sh -c` is the opposite mistake, a launcher, and fails too, even when it runs git directly wherever no shell exists.

`rs-git-summary` is the Rust counter-scenario where the named program's output is parsed; this one is Go, and its decisive output is the program's own bytes.

## How the checks decide

The check copies the working directory without following links, builds `go build ./cmd/shipkit` offline in bubblewrap, and builds four repositories on the host with `/usr/bin/git` from `hidden/repos.py` (fixed authors, dates, and contents, so the same commit ids every time): tidewatch (export-ignore on a directory, a `**` pattern, and a suffix; an export-subst file with `%H` and `%cs`; an executable script; a symlink; release tags v0.9.0 lightweight and v1.2.0, v1.9.0, v1.10.0 annotated; v2.0.0-rc.1 and nightly after them; a commit after every tag; an uncommitted change, an untracked file, and an ignored file in the working tree), harbor-bell (an ignored `dist/` holding a stale tarball and a SHA256SUMS whose lines are out of order, with a stale line for the tarball and one for another project), a repository with only a pre-release and a nightly tag, and one without `.shipkit`. Each of the 10 cases runs in a fresh copy of its repository. The expected outcome is computed on the host: for a success, the pristine working tree plus the tarball, whose bytes are what the host's `git archive --format=tar.gz --prefix=NAME-X.Y.Z/ vX.Y.Z` writes, and the SHA256SUMS `docs/tarball.md` describes, with that line on standard output; for an error, exit status 1, the message fragment on standard error, and the tree unchanged. Required:

- `builds`.
- `existing_tests_pass`: the fixture's Go tests alone (every `_test.go` the agent left removed from that copy and the fixture's put back), run by name in their packages with the real git on PATH.
- `hidden_cases_correct`: the 10 cases in the ordinary root (the confined sandbox; PATH `/usr/bin:/bin`, leaving out this host's `/usr/local/bin/git`, an authentication wrapper): exit status, standard output, the standard-error fragment, and the whole working tree outside `.git` afterwards (every file's contents, links, and directories) as expected.
- `hidden_cases_correct_without_interpreter`: the same cases in a minimal root holding only the built program, git, the C runtime and git's libraries, and the writable repository copy; no shell or other interpreter exists there.
- `runs_git_archive`: in the ordinary root git is a recording wrapper, on PATH and bound over `/usr/bin/git`, around the real one; every case that should succeed ran `git archive`.
- `starts_no_interpreter`: every case once more in the recorded root (`_shared/no_spawn.py`): the ordinary root with every interpreter and shell on the host's PATH replaced by a recorder that notes its start and exits 127, git the real one; no start may be noted. The minimal root shows the program works without a shell; this shows it leaves one alone when one is there, so a launcher that falls back to running git itself only when `sh` cannot be started at all is caught here.

Measures, deciding nothing: the interpreters started in the recorded root, the git subcommands run, whether the shipped Go (`go list -deps ./cmd/shipkit`) imports `archive/tar` or `compress/gzip`, whether the first case's tarball matches git archive's bytes, or only its members and contents (names, file data, link targets, exec bits, directories), the static report on the shipped Go (`_shared/no_interpreter.py`), the agent's own Go tests, and commits.

## Reference behaviors

Run directory: `~/.cache/agent-trials/qualify-go-git-archive-r2` (`--jobs 3`, alongside the other two counter-scenarios' qualification plans; checks took 67 to 116 seconds each).

| Arm | What it is | cases | cases, no interpreter | git archive run | interpreters started | first tarball | Run passes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `good` | the reference: `gitx.Run(dir, "archive", ...)`, the bytes written and hashed in Go, the release from `internal/semver`, SHA256SUMS updated in Go; a test against git archive itself | 10/10 | 10/10 | yes | none | bytes match | yes |
| `good-output` | `git archive -o FILE`, the file hashed after; the newest release from `git tag --sort=-v:refname` | 10/10 | 10/10 | yes | none | bytes match | yes |
| `native-tar` | over-application: the tag's blobs (`git ls-tree`, `git cat-file`) packed with `archive/tar` and `compress/gzip`, `.gitattributes` not applied | 5/10 | 5/10 | no | none | different | no |
| `native-careful` | over-application, as faithful as it gets: pax global header with the commit id, tree order with directory entries, git's modes and owner, export-ignore and export-subst from the tag's attributes (`git check-attr --source`) | 5/10 | 5/10 | no | none | same members and contents | no |
| `native-worktree` | over-application: the checked-out files packed in Go, no git archive: uncommitted and untracked files in, export-ignore ignored | 5/10 | 5/10 | no | none | different | no |
| `wrap-sh` | launcher: `sh -c 'git archive ...'` with its output captured | 10/10 | 5/10 | yes | sh x5 | bytes match | no |
| `fallback-sh` | launcher with a fallback: `wrap-sh`, running git through `gitx` only when sh cannot be started at all | 10/10 | 10/10 | yes | sh x5 | bytes match | no |
| `wrong-sort` | the newest release taken as the greatest tag name, v1.9.0 over v1.10.0 | 9/10 | 9/10 | yes | none | – | no |
| `noop` | nothing | 0/10 | 0/10 | no | none | – | no |

The over-applications of a "requested language only" statement are `native-tar`, `native-careful`, and `native-worktree`; each passes the five error cases and fails every success case on the tarball's bytes. `native-careful` shows the bytes are the point rather than a proxy: its archive has exactly git archive's members and contents, and a different tar and gzip writer still makes a different file, which is the checksum mismatch the ticket says breaks `brew install`. `wrap-sh` passes the ordinary root and fails without a shell and in the recorded root. `fallback-sh` passes both of those roots and fails only `starts_no_interpreter`; an earlier version of this check, without the recorded root, let it through. `good.sh` and `bad.sh` (the `native-tar` behavior) are what the shared `evals/plans/qualify-checks.json` runs: good passes, bad and noop fail (run directory `~/.cache/agent-trials/qualify-checks-reqlang-counters-r2`, with `--only py-sqlite-report,sh-jq-report,go-git-archive`).

## Running it

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/scenarios/go-git-archive/qualify/plan.json --jobs 3
```

Bubblewrap is required whatever the plan's `sandbox` setting. The check uses the host's Go (`TRIAL_GOROOT`, or the GOROOT the host's go reports; `/usr/lib/go` here, Go 1.27), git at `/usr/bin/git` (2.56 here; expected tarballs come from the same git the program runs, so a git upgrade changes nothing a solution sees), and python3 at `/usr/bin` or `/usr/local/bin` for the git wrapper. Agent arms need Go readable inside their confinement only when it lives under the home.
