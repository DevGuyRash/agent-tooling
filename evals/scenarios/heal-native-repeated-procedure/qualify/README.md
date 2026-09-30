# Qualifying heal-native-repeated-procedure

Same repository fixture, same embedded problems, same `required` checks and judge as
[`heal-repeated-procedure`](../../heal-repeated-procedure/), except that the seven session logs move
out of the repository (`fixture/.local/agent-sessions/*.md`) and into the run's own private `$HOME`,
in each host's real current record format: four Codex rollouts under
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` and three Claude Code transcripts under
`~/.claude/projects/<encoded-cwd>/<session>.jsonl`, dated relative to setup time so a plain "recent
sessions" pass finds them whenever the trial actually runs. `setup.sh` writes them with
[`gen_native_logs.py`](../gen_native_logs.py); see its module docstring for the exact shapes, what
they were checked against on this machine's own `~/.codex/sessions` and `~/.claude/projects`, and
what was deliberately left unattempted rather than guessed at.

This scenario went through an audit against the real trial runtime (checked out from GitHub
`main@8fb792b`) that found ten issues; the fixes below responded to the ones that held and were
fixable from scenario files alone (see "Findings addressed" and "Out of scope" below for exactly
which, and why some could not be).

## Checks that changed from the source scenario

- `native_logs_unchanged` replaces `transcripts_unchanged` (git-ignored-file diffing inside the
  repo), since the logs no longer live in the repository. It no longer compares the run's `$HOME`
  against a byte-identical duplicate copy of every log (a duplicate the agent under test could read
  and could tamper with in lockstep to defeat the check - see finding 6 below); instead `setup.sh`
  writes a single sha256 manifest, one line per file, to `$TRIAL_HARNESS/.setup-manifest.sha256`, and
  the check re-hashes each live file and compares digests.
- `log_evidence_reported` (new, `required`): the final message must report at least one fact that
  exists only in the session logs, never in the repository - the developer's "golden update took
  longer than the change itself. Again." complaint, the approved-publish exchange, or at least two of
  the four regeneration slips (missing `--indent`, only the expected file regenerated, the wrong
  `--bank`, the skipped pretty-print step). Without this, the scenario could be, and was, passed by a
  reference (`bad.sh`, and in the source scenario generally) that never looked at a log at all - see
  finding 1 below.
- `opened_native_logs` (new, diagnostic only, not `required`): whether the final message, an executed
  command, or an agent message mentions `.codex/sessions`, `.claude/projects`, `gather.py`, or
  `digest.py` - reported per run so a real trial can see whether an arm actually opened the logs
  instead of only inferring their contents. Not a `required` check, since a healing agent that already
  knows the facts from an earlier turn's exploration shouldn't be forced to re-cite a path.
- `changelog_changed` now compares the live `CHANGELOG.md` against the run's own initial commit
  (`git show <initial-head>:CHANGELOG.md`) instead of the static `fixture/CHANGELOG.md` on disk, since
  `setup.sh` now writes a per-run, date-shifted `CHANGELOG.md` (see "Recent, non-contradictory dates"
  below) that no longer matches the fixture file byte for byte.

Every other `required` check, the ANSWER_KEY (aside from one sentence reworded below), and the judge
question/`pass_when` are the same as the source scenario, since none of them named the
`.local/agent-sessions/` path in the first place.

## Findings addressed

From the audit (numbers match its report):

1. **Log-only evidence required.** Added `log_evidence_reported` and `opened_native_logs` (above).
2. **Codex's own `$CODEX_HOME` vs. this scenario's `$HOME`.** Resolved in the trial runtime (2.1.2): every executor sees the planted logs where its host keeps them: Codex runs keep `CODEX_HOME` at `$HOME/.codex` inside the run's private home (trial runtime 2.1.2), the same `$HOME` where `setup.sh` plants the sessions, and Claude Code runs read `$HOME/.claude`. Earlier runtimes put `CODEX_HOME` beside that home, where a Codex arm could not see the planted Codex sessions; run this scenario on 2.1.2 or later.
3. **Claude Code's project-directory encoding.** Fixed: `encode_cwd` now replaces every character
   that is not `[A-Za-z0-9]` with `-` (checked against the installed 2.1.281 binary's own encoder,
   disassembled: `e.replace(/[^a-zA-Z0-9]/g,"-")` - it does not spare `_` or `-` themselves, so a job
   id's `__` becomes `--`, not `__`). `gen_native_logs.py` now also refuses to run (nonzero exit, which
   fails `setup.sh` loudly) when the encoded name would exceed the 200 characters Claude Code itself
   truncates at, rather than silently planting a name a real client would never produce.
4. **Log format fidelity.** Partially addressed - see "Format fidelity: what changed and what didn't"
   below for exactly what was fixed, what was deliberately left alone, and why.
5. **Session and git-history dates.** Fixed - see "Recent, non-contradictory dates" below.
6. **Visible, tamperable snapshot.** Fixed: replaced the byte-identical `$TRIAL_HARNESS/native-logs/`
   copy with a sha256 manifest (above). "Ideally outside the job directory" (the audit's stretch goal)
   is not achievable under the current runtime: `Run.read()` refuses any path that does not resolve
   inside the job directory, so a check literally cannot compare against anything stored elsewhere.
7. **Scenario/arm names in log metadata.** Not fixed - see "Out of scope" below.
8. **`fixture/.gitignore` dropping `.local/`.** Fixed: restored the line, unchanged from the source
   scenario's `.gitignore`, so an agent's own scratch notes under `.local/` stay ignored instead of
   being picked up as tracked changes by `git add -A`.
9. **Findability claim untested against a real agent.** Not fixed - see "Out of scope" below.
10. **ANSWER_KEY overclaiming what the judge can verify.** Fixed: reworded the sentence about session
    logs to say plainly that the judge is not given them directly and accepts the agent's account of
    them at face value, rather than implying the judge can check an observation against the logs
    itself.

## Format fidelity: what changed and what didn't

Fixed, each checked against this machine's own real logs or well-established public API shape:

- **IDs are UUIDv7, not uuid4.** Real Codex session ids observed on this machine (e.g.
  `01a0ca89-ce02-7a71-...`) are time-ordered UUIDv7; `gen_native_logs.py` now generates every id (Codex
  session/thread/item/turn ids, Claude Code's `uuid`/tool-use ids) the same way, from each event's own
  timestamp, with a small self-contained generator (no dependency on Python 3.14's `uuid.uuid7`).
- **Codex message content is a block array**, `[{"type": "text", "text": ...}]`, not a bare string -
  confirmed against the item structure of a real rollout on this machine. `digest.py`'s `_text()`
  helper already handled both shapes, so this is a compatible change (verified: `digest.py` still
  reads all 7 sessions, 12 user messages, 4 failed commands from the regenerated fixture).
- **Rollout folder and filename use local wall-clock time**; every timestamp field inside the file
  stays UTC - confirmed against this machine's own rollouts (a folder dated hours behind a payload
  timestamp of the same event, consistent with local-time naming on a machine west of UTC).
- **`cli_version` bumped** to `0.159.2` (Codex) and Claude Code's `version` to `2.1.281` - both the
  actually-installed versions on this machine, replacing stale placeholders.
- **`gitBranch` now tracks each session's own `git switch` commands** instead of staying `"main"`
  throughout - the branch name was already present in the same command text, so this only reads what
  was already there.
- **The embedded traceback** in the schwab-parens session no longer names a hardcoded, disconnected
  path (`/home/dev/repos/ledgerline`); it now substitutes the run's actual working directory, so the
  path in a tool-result string matches the session's own recorded `cwd`.
- **Claude Code assistant lines carry a real Anthropic Messages API envelope** (`message.id`,
  `usage`, `stop_reason`, a top-level `requestId`) instead of a bare `{role, content}` pair.
- **Each session keeps its own original time of day** (from `heal-repeated-procedure`'s source
  transcripts - 09:02:18, 15:12:05, ... instead of every session landing at the same instant every
  session inherited from "now" before this fix).

Deliberately not attempted, and documented rather than guessed at:

- Codex's `custom_tool_call`/`FileChange`/`turn_context`/`token_count` records, and the much higher
  line-count/noise ratio of a real rollout. The audit's own cited specifics for this (an exact
  `codex_exec`/`codex-tui` version and an event model with zero `item_completed` records) did not hold
  up against this machine's own real, current rollouts, which do carry `item_completed`
  `CommandExecution`/`AgentMessage`/`UserMessage` items - inventing the audit's more specific,
  unverified claims about additional record types risked replacing a stale-but-structurally-plausible
  fixture with a wrong invented one. Reproducing them faithfully would need an actual `codex exec` run
  to observe, which costs API usage and was out of scope for this pass.
- Claude Code's `toolUseResult` for `Read`/`Edit` (real transcripts carry the actual file content or
  diff), and `Edit`'s `old_string`/`new_string` input fields. Both would require inventing plausible
  multi-line code diffs against `ledgerline/normalize.py`'s evolution across `history/c0`..`c6` that
  this fixture has no source for; a wrong invented diff is worse than the current honest placeholder
  (`"(file contents)"`/`"(edited)"`). `toolUseResult` *was* added for `Bash`, where the real output
  text was already in hand.
- Claude Code's `attachment`/`system`/`file-history-snapshot`/`last-prompt` line types and `entrypoint`
  field. Unverified without a real `claude -p --bare` transcript to check the exact shape against.

## Recent, non-contradictory dates

`setup.sh` used to rebuild the git history at fixed 2026 dates while `gen_native_logs.py` placed the
native logs on a calendar relative to *now* - so the gap between "the tag says 2026-09-12" and "the
logs are dated last week" grew by one day with every day this scenario gets reused. `setup.sh` now
computes one day-shift (so the last historical commit lands one day before whenever the trial actually
runs) and applies it to every commit's `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` (the annotated tag
inherits its tagger date from the same environment automatically), and to the two release dates baked
into `CHANGELOG.md` text (`sed` after every `state()` copy, including the pre-rebuild snapshot used for
the self-check, so `setup.sh`'s own "does the rebuild reach the fixture state" diff stays consistent).
The shift preserves each date's original time of day and the story's original day-to-day spacing - only
the calendar lands differently. Verified end to end (see "Validation performed against the real
runtime" below): with "today" at 2026-09-30, the rebuilt history's release commits land at
2026-09-08/2026-09-23, matching `CHANGELOG.md`'s own "0.8.0 (2026-09-08)"/"0.9.0 (2026-09-23)" text
exactly, and the last commit lands 2026-09-29.

`gen_native_logs.py` separately keeps each of the 7 sessions' own original time of day (from
`heal-repeated-procedure`'s source transcripts) instead of all 7 landing at the exact same clock time
every session previously inherited from "now" at setup.

## Reference behaviors

Run with the `command` executor, no judge (a judge question with no judge configured is reported
`judge-missing`, which is expected and ignored here - only the `required` checks below decide):

```json
{"name": "qualify", "repeats": 1,
 "arms": {"good":     {"executor": "command", "command": "sh \"$TRIAL_SCENARIO_DIR/qualify/good.sh\""},
          "bad":      {"executor": "command", "command": "sh \"$TRIAL_SCENARIO_DIR/qualify/bad.sh\""},
          "findable": {"executor": "command", "command": "sh \"$TRIAL_SCENARIO_DIR/qualify/logs_findable.sh\""}},
 "scenarios": ["scenarios/heal-native-repeated-procedure"]}
```

## Validation performed against the real runtime

Requalified after the fixes above, via `trial.py run` from a clean checkout of `origin/main`
(`8fb792b`, confined, bubblewrap 0.13.0 present), into a fresh run directory - `good`/`bad`/`findable`
as `command` arms against this scenario directory:

| Reference | `regen_automated` | `documented_regen_works` | `stray_files_handled` | `log_evidence_reported` | other required checks | `native_logs_unchanged` | `opened_native_logs` | Outcome |
|---|---|---|---|---|---|---|---|---|
| `good.sh` | true | true | true | true (complaint + all 4 slips + release gate) | all true | true | false | passes every `required` check (verified) |
| `bad.sh` | false | false | false | false | rest true | true | false | fails exactly `regen_automated`, `documented_regen_works`, `stray_files_handled`, `log_evidence_reported` (verified - one more than before `log_evidence_reported` existed, since `bad.sh`'s final message cites no fact from the logs) |
| `logs_findable.sh` | false | false | false | true (complaint + 3 of 4 slips) | rest true (nothing to touch) | true | true | not a heal attempt - fails the same repository-change checks as `bad.sh`, but (unlike `bad.sh`) passes `log_evidence_reported` and `opened_native_logs`, demonstrating that finding the log evidence and fixing the repository are independent (verified) |

`logs_findable.sh` is not a "near-miss" heal - it is the direct answer to *"if you were able to find
this stuff, I'm sure the models would be able to too"*: proof that the fixture does not depend on any
purpose-built parser to be discoverable, only on tools any agent already has. Run in isolation it also
printed, to its own stderr (captured in `events.jsonl` for a `command` arm): the 7 file paths under
`$HOME`, the exact count per host (codex 4, claude 3), all 12 user turns in order, the file containing
the developer's complaint, and the file for each of the four slips - all before the python3 step even
ran, which independently confirmed 5 sessions ran the manual `json.tool --sort-keys` regeneration step
(matching the answer key's "five sessions repeated it").

A tampering check was run directly against this requalified run (not part of the reference set above,
just to confirm the manifest-based check still has teeth after replacing the duplicate-copy approach):
appending one line to a planted Codex rollout file and rechecking (`trial.py recheck`) flipped
`native_logs_unchanged` to `false`; the three references above, none of which touch `$HOME`, all read
`true`.

`plugins/agentic-design-and-evaluation/skills/self-healing/scripts/digest.py` was run directly against
one of the requalified runs' generated `$HOME` tree: found all 7 sessions, 12 user messages, and 4
failed commands - unchanged from before the format-fidelity fixes above, confirming they stayed
compatible with this repository's own log reader.

## What was and wasn't copied

Directory layout and file-naming were read from this machine's own `~/.codex/sessions/YYYY/MM/DD/`
and `~/.claude/projects/<encoded-cwd>/` (structure and file-naming only - no session content was read
into this fixture). The Codex JSON shape (`session_meta` / `event_msg` -> `item_completed` ->
`UserMessage`/`AgentMessage`/`CommandExecution` with `command`/`exit_code`/`aggregated_output`) was
read from this machine's own recent `rollout-*.jsonl` files (key names and item types only, never
message text) and cross-checked against
`plugins/agentic-design-and-evaluation/skills/self-healing/scripts/digest.py`'s `read_codex()`, which
this repository already maintains as its own definition of the format.

Every native Codex and Claude Code log actually on this development machine turns out to be written by
a desktop wrapper - "Codex Desktop" (`originator`, `cli_version` fields unlike the CLI's own
`codex_cli_rs`) for Codex, and a bridged client (`bridgeSessionId`, `ownerAccountUuid`, ...) for Claude
Code - not by vanilla `codex exec`/`claude -p --bare`, which is what this repository's trial runtime
actually invokes. Since `digest.py`'s `read_codex()`/`read_claude()` (this repository's own definition
of "the current native log format") target the documented vanilla shapes, this fixture follows those
rather than either wrapper's own bridged one: `digest.py --codex ... --claude ...` run against the
generated fixture parses all 7 sessions correctly (`sessions: 7`, `user_messages: 12`, `failed
commands: 4`), which is the strongest available confirmation that the format matches what this
repository's own log reader expects of "current" native logs.

## Out of scope (not fixed by this scenario)

These findings held but could not be fixed from scenario files alone, or need something this pass did
not have:

- **Finding 2, `CODEX_HOME` vs. `$HOME`.** Resolved in the trial runtime 2.1.2; see "Findings addressed" #2.
- **Finding 7, scenario/arm names in log metadata.** The job directory name
  (`heal-native-repeated-procedure__<arm>__r<rep>`) is the scenario's own `cwd`, which `trial.py`'s
  `_run_job_once` builds from the scenario name and arm name and which necessarily ends up in
  `session_meta.cwd`, every Claude Code line's `cwd`, and the Claude Code project-directory name -
  this is a property of the shared runtime's job-directory naming (and, for arm names, of whatever
  plan file the actual experiment runs), not something `gen_native_logs.py` can avoid while still
  faithfully recording the `cwd` it's given. Renaming this one scenario out of the matched
  `heal-native-{mixed,clean,repeated-procedure}` trio would also break the parity the experiment
  likely depends on across all three - a decision for whoever sets the experiment's naming, not a
  scenario-local edit.
- **Finding 9, findability untested against a real agent.** `qualify/logs_findable.sh` proves the logs
  are readable with ordinary tools; it does not prove an uninformed agent will think to look. That
  needs a small real no-skill run per executor, which needs API keys/cost and was out of scope here
  (see "Validation performed against the real runtime" for what was actually run: three `command`
  reference scripts, no real agent).
- **The unattempted part of finding 4** - see "Format fidelity: what changed and what didn't" above.
