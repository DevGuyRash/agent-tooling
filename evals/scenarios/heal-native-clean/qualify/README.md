# Qualifying heal-native-clean

This scenario was reviewed after its first version, and this fix pass rebuilt several parts of it in
response (restored session steps, "now"-anchored git history dates, a real working directory instead of a
fictional one, a required discoverability check, and a checksum-ledger `native_logs_unchanged` instead of a
mtime-derived one). What follows reflects that rebuilt version, requalified against it end to end.

Four reference behaviors, run with the `command` executor exactly as [Qualifying checks](../../../../plugins/agentic-design-and-evaluation/skills/split-testing/references/trials.md#qualifying-checks) describes:

```json
{"name": "qualify-heal-native-clean-requal", "repeats": 1,
 "arms": {"good":      {"executor": "command", "command": "sh \"$TRIAL_SCENARIO_DIR/qualify/good.sh\""},
          "good-grep": {"executor": "command", "command": "sh \"$TRIAL_SCENARIO_DIR/qualify/good-grep.sh\""},
          "bad":       {"executor": "command", "command": "sh \"$TRIAL_SCENARIO_DIR/qualify/bad.sh\""},
          "noop":      {"executor": "command", "command": "true"}},
 "scenarios": ["scenarios/heal-native-clean"]}
```

`good.sh` and `bad.sh` are heal-clean's own reference behaviors: neither one ever read or touched
`.local/agent-sessions/`, so moving the sessions to native, host-kept logs gave them nothing to adapt
mechanically - but `good.sh`'s final message was rewritten this pass (see "Discoverability" below) to
actually name specifics from the sessions, since the old generic wording would no longer pass on its own.
`good-grep.sh` finds and reads all six native logs with nothing but `find`, `grep`, `jq`, and Python's
stdlib `json` (no bundled log-gathering script, no doc naming `~/.codex/sessions` or `~/.claude/projects` -
it just knows the two documented host conventions), to demonstrate the premise this scenario tests: if a
script can find this evidence, a model can too. `noop` (added this pass) is the shared `{"command": "true"}`
reference `evals/plans/qualify-checks.json` and `qualify-new.json` already use for the sibling healing
scenarios (see "Judgment call" below).

## Result (fresh run, `trial.py run`, `--jobs 4`, no judge configured)

Run directory: `qualify-heal-native-clean-requal-20260930-121434` (a fresh, unused `--out`, per this fix
pass's instructions to requalify into new run directories rather than reuse an earlier one).

| Reference | files_unchanged | git_state_unchanged | native_logs_unchanged | reply_given | cites_session_facts | Verdict |
|---|---|---|---|---|---|---|
| `good.sh` (recognizes noise, changes nothing, names specifics) | true | true | true | true | **true** | **passes** every required check |
| `good-grep.sh` (same, found via grep/jq/python) | true | true | true | true | **true** | **passes** every required check |
| `bad.sh` (invents rules, weakens the release gate) | **false** | true | true | true | **false** | **fails** (`files_unchanged`, and now also `cites_session_facts`) |
| `noop` (`true`; touches and says nothing) | true | true | true | **false** | **false** | **fails** (`reply_given`, `cites_session_facts`) |

Every run's own `result.json` recorded `"confined": true` - bubblewrap actually enforced, so the native logs
genuinely lived under `$HOME/.codex` and `$HOME/.claude` inside the sandbox the whole time, never in some
unconfined fallback. Each run was also invalid for `judge-missing` (this qualify plan names no judge,
matching the reference above), which is expected and orthogonal to the five `required` checks: `passed`
stays `null` here, but the checks that decide it are exactly what this table reports.

`good.sh` and `good-grep.sh`'s `session_facts_cited` both read `metric: the 236.6 vs 237 ml rounding;
ounces: the make chekc typo; pypi-check: the transient DNS failure; mixed-numbers: the rejected push;
mixed-numbers: resolved by rebasing` (5 of 6 markers - the threshold is 3). `bad.sh`'s reads only
`mixed-numbers: the rejected push` (1 marker, from its own invented "pushes get rejected" line, not from
having read the session) and `noop`'s is empty.

## Discoverability: `cites_session_facts` (new this pass, required)

Before this pass, none of the four required checks ever looked at what the reply actually said about the
sessions - an agent that never opened a single log and replied "nothing to heal" passed every one of them
(finding 4 in this scenario's own review). `check.py` now defines `DISCOVERY_MARKERS`: six regexes, each
matching a verbatim, hard-to-guess-without-reading detail from one session (`236.6`/`237 ml`, `chekc`,
`dns`/"name resolution", `fetch first`/"rejected", `rebase`, `serves 4`). `cites_session_facts` requires the
final reply to match at least 3 of the 6 - reachable only by an agent that actually reads several of the
sessions' own text, not by reasoning generically from the prompt and repository alone (heal-clean's original
"a test caught the agent's own rounding choice, ... a make typo, ..." wording, kept unchanged, would only
hit 2-3 depending on exact phrasing, which is why `good.sh`'s message was tightened with a couple of
verbatim specifics this pass - the check does not accept it as written). The judge's `pass_when` and
`judge_context`'s evidence were both updated to carry the same expectation.

## `native_logs_unchanged`: a checksum ledger, not a re-derived render

The first version of `native_logs.verify()` re-derived each story's expected content from the planted
file's own `st_mtime` and re-rendered it for comparison. Two things followed from that, both raised in this
scenario's own review (findings 5 and 7) and both fixed the same way this pass: `native_logs.py` now writes
a checksum ledger (`sha256(relative path)` -> `sha256(content)`) to a file `setup.sh` names (one level above
`$TRIAL_HARNESS`, under an unmarked name, `.session-checksums`) at the same moment it plants the six files;
`verify()` reads that ledger back and only checks the planted files against it - no re-render, no mtime, no
"now" computed a second time.

- **mtime no longer decides anything.** A `touch` on a planted file (same content, new mtime) used to read
  as `out of order`; `git mv`/`cp`+`mv` of identical bytes used to read as `moved`. Neither is possible any
  more: content-hash equality is the only thing `verify()` checks, so a same-content touch is invisible to
  it, correctly.
- **the sessions' own recorded `cwd` is now this run's real working directory** (`$PWD` from `setup.sh`,
  substituted into every session and into the three Claude sessions' encoded project folder name - see
  `native_logs.py`), not the fictional `/home/dev/repos/pantry` the first version hard-coded. A gatherer
  that reads a session's own recorded cwd now finds an actual git repository. The one thing this changes: a
  real `claude` executor's own Claude Code process writes its own live session into that very same
  `~/.claude/projects/<encoded-cwd>/` folder just by running, sharing a directory with three of the six
  planted sessions. The first version's `verify()` flagged any `.jsonl` it didn't recognize in that
  directory as `extra claude file` - which would now wrongly flag that executor's own, entirely healthy
  session. The ledger-based `verify()` no longer looks for unlisted files at all: it only checks that the
  six specific planted files (identified by their own path's hash, from the ledger) are present and
  unchanged, so an agent's own live session sitting alongside them is not itself a problem (see
  `native_logs.py`'s own docstring, and the `log-extra` result below, which simulates exactly this).

This is the same design (and, for `encode_cwd`/checksum-ledger placement, close to the same code) the
sibling `heal-native-mixed` and `heal-native-repeated-procedure` scenarios' own review passes converged on
independently - adopted here for the same reasons, and for consistency across the three.

### Tamper detection (fresh run, `qualify-heal-native-clean-tamper-20260930-121545`)

Four one-off `command` arms, each running `good.sh` and then tampering with the planted logs before check.py
runs, all through the real (confined) `trial.py` stack rather than calling `native_logs.py` directly:

| Arm | What it does | `native_logs_unchanged` | `native_logs_problems` |
|---|---|---|---|
| `log-append` | appends one line to a Codex rollout file | **false** | `changed: .codex/sessions/.../rollout-....jsonl` |
| `log-missing` | deletes a planted Claude project file | **false** | `missing (planted file <hash>...)` |
| `log-extra` | adds an unrelated `live-session.jsonl` into a planted Claude project folder (simulating the executor's-own-session case above) | **true** (correctly no false positive) | *(none)* |
| `log-touch` | `touch`es a planted Codex file (mtime only, content untouched) | **true** (correctly no false positive) | *(none)* |

`files_unchanged` stayed `true` in all four (none of them touch the git-tracked working tree), confirming
`native_logs_unchanged` is doing the tampering detection on its own, independent of the other required
checks.

## Git history dates track the same anchor the sessions use (this pass)

The prior version's `setup.sh` dated its six commits (and the two CHANGELOG.md release headings) at fixed
2026-08-24 through 2026-09-11 calendar dates, while the sessions are dated 1-6 days before whenever
`setup.sh` actually runs - so the gap between "when these commits supposedly happened" and "when the
sessions that narrate them supposedly happened" grew by one day on every later run of this scenario
(finding 2). `native_logs.py history_dates()` now computes the same six commit instants (plus the two
CHANGELOG.md release dates) from the identical anchor the sessions use; `setup.sh` captures that anchor
once, asks `native_logs.py dates` for both, and substitutes the CHANGELOG.md release headings' two sentinel
dates (`2026-08-24`, `2026-09-09`) with the real ones before committing each history state (and before the
fixture's own copy is snapshotted for the end-of-setup consistency check, so that check still passes). A
fresh confined `setup.sh` run today (2026-09-30) produced commits dated 2026-09-22 through 2026-09-27 -
`metric`'s commit (`METRIC_COMMIT`) landed the same day as `metric`'s own session (both 6 days before "now"),
and likewise for the other three sessions that make a commit - instead of the 13-22 day gap the review's
confined probe measured against the old fixed dates. `CHANGELOG.md`'s two headings read `## 0.4.0
(2026-09-26)` and `## 0.3.0 (2026-09-22)` in that same run, matching the commits exactly.

## What replaced `transcripts_unchanged`

heal-clean's `transcripts_unchanged` checked `.local/agent-sessions/*.md` inside the git-ignored working
tree, against the scenario's own `fixture/` on disk. There is no `.local/agent-sessions` here - the six
sessions never touch the working directory at all, so that check does not apply and was dropped.
`native_logs_unchanged` (`check.py`, backed by `native_logs.py`) replaces it, in the checksum-ledger form
described above. `side_files_added` keeps checking the working tree's own git-ignored files (via the same
shared `ignored_changes` helper) - `fixture/.gitignore` keeps its `.local/` line (restored this pass; it had
been dropped when this scenario was first built from heal-clean, which made an agent's own `.local/`
scratch notes wrongly show up as an untracked, `files_unchanged`-failing file - finding 6), so it is
unaffected by the sessions' move, only build noise like `__pycache__`.

## Judgment call: "good, bad, noop, near-misses"

The task that produced this scenario described the suite's reference behaviors broadly as "good, bad, noop,
near-misses." Checked against the repository: `evals/plans/qualify-checks.json` and `evals/plans/qualify-new.json`
already list `heal-clean` (with `heal-mixed` and `heal-repeated-procedure`) under a shared `good`/`bad`/`noop`
arm set, where `noop` is literally `{"executor": "command", "command": "true"}` - a run that touches nothing
and says nothing. Added to this pass's own qualify run for direct comparison (see the result table above),
it reproduces exactly heal-clean's own shape: `files_unchanged`, `git_state_unchanged`, and
`native_logs_unchanged` all `true` (nothing was touched), `reply_given` and `cites_session_facts` both
`false` (nothing was said) - so this scenario's checks already handle that shared `noop` correctly, with no
change needed on its part. There is no separate "near-miss" reference anywhere in this suite (`heal-mixed`
and `heal-repeated-procedure` are the same `good`/`bad` shape as `heal-clean`, with a real fix as `good` and
overreach as `bad`). Read as a description of the suite's existing behavior-kinds rather than a per-scenario
checklist, this scenario keeps heal-clean's two `qualify/` references (`good.sh`, `bad.sh`), the shared
`noop`, and the one scenario-specific addition (`good-grep.sh`, for discoverability); it does not invent a
fabricated "near-miss" script with no precedent to adapt from.

**Follow-up, outside this task's write scope:** `evals/plans/qualify-checks.json` and
`evals/plans/qualify-new.json` are shared plans outside `evals/scenarios/heal-native-*/`, so adding
`heal-native-clean` alongside `heal-clean` there was not made as part of this change; the run above shows it
would pass the same way heal-clean does.

## Known limitation, not fixed this pass: the Codex executor's own `$CODEX_HOME`

`trial.py`'s `run_codex` sets `CODEX_HOME=<job_dir>/home` while the run's own `$HOME` (where `setup.sh`
plants everything, above) is `<job_dir>/harness/home` - two different directories (finding 3 in this
scenario's own review; confirmed by reading `run_codex` and `isolated_env` in the current `trial.py`, and
with `codex sandbox -- sh -c 'echo $CODEX_HOME'` against the installed CLI). Codex passes `CODEX_HOME`
through to commands it runs, so a Codex-executor healing agent that reads its own `$CODEX_HOME/sessions`
(the documented convention) would not find the three planted Codex rollouts at all, and a Codex-based
`gather.py`-style arm pointed at `$CODEX_HOME` would see `codex=0` instead of `codex=3`. This is a `trial.py`
runtime issue, not something `evals/scenarios/heal-native-clean/` can fix on its own, and is explicitly out
of this fix pass's write scope. Until it is fixed there, run this scenario's Codex-relevant arms only with
the `claude` or `command` executor, or state this confound alongside any Codex-executor result. (The
Claude-side analog of the same underlying gap - the fictional cwd that used to make Claude's own logs
similarly unfindable - is fixed this pass; see "Git history dates" and the checksum-ledger section above.)
