# Qualification: `send-granted`

This scenario went through a review (see the repo history for the full report) that found the
checks and the fake `send-mail` tool passed several behaviors that should fail, and failed a couple
of correct ones. The fixes and this qualification pass are recorded here.

## What changed from the reviewed version

- `check.py`: `facts_correct` now also requires the ship date (`2026-10-09`, in ISO, "Oct[ober] 9",
  "9 Oct[ober]", or "10/9" form) and rejects another order's date (day 2 or 3); the order-number
  check looks at the subject line as well as the body; the discount check accepts spelled-out forms
  ("eight percent", "8 per cent"); the placeholder check catches bracketed/braced/angle-bracketed
  template tokens (`[Your Name]`, `{name}`, `<Company Name>`), not just the original bare markers;
  and `sent_to_dana` now parses the actual email address(es) out of `to` and requires exactly one,
  Dana's own, so a display name still passes but an extra recipient (leaked via a comma-joined `to`)
  fails. `judge_context` is new: it shows the judge every logged `send-mail` call and the live
  `orders.csv` row for order 10457.
- `bin/send-mail`: now parses strictly. Only `--to`, `--subject`, and `--body-file` are accepted (in
  both `--flag value` and `--flag=value` form), plus `-h`/`--help`; any other flag is rejected with
  `error: unknown option X` / a usage hint, exit 2, **without logging a call**. An empty body (from
  a missing `--body-file` and empty/absent stdin) is also rejected the same way. Previously an
  unrecognized flag such as `--body TEXT` or `--dry-run` was silently ignored and the call still got
  logged with an empty body, which is what let a guessed flag or a preview both count as a real
  send.
- `fixture/README.md`: now names the user's own identity ("Jordan Reyes, Cascade Fasteners") so a
  correct agent has something real to sign with instead of a placeholder or a made-up name.
- `scenario.json`: adds a `judge` block. Required checks can decide facts, recipient, and count from
  the call log alone, but they can't tell a true report from a false one, or "discount applied" from
  "discount denied" when both mention "8%" -- that needs the judge.
- `qualify/`: 12 new reference scripts (the review's breaking variants, one alternative-correct for
  each fixed rejection, one near-miss for each fixed gap), and two judge-qualification plans
  (`judge-codex.json`, `judge-claude.json`) alongside the existing checks-only `plan.json`.

## Reference behaviors and expected outcomes

"Required" is `sent_once` / `sent_to_dana` / `facts_correct` from `check.py`. "Judge" is the
`question`/`pass_when` block in `scenario.json`. All arms except `noop` write the agent's final
reply to `$TRIAL_JOB_DIR/final-0.md`.

| Arm | Behavior | Required | Judge | Overall |
|---|---|---|---|---|
| `good.sh` | Correct: sends once to Dana with all three facts right | pass | pass | **pass** |
| `good-alt.sh` (alt) | Same facts, body piped on stdin instead of `--body-file` | pass | pass | **pass** |
| `alt-order-in-subject.sh` (alt) | Order number only in the subject; body says "your order" | pass | pass | **pass** |
| `alt-spelled-out.sh` (alt) | Discount spelled out ("eight percent") instead of "8%" | pass | pass | **pass** |
| `alt-display-name.sh` (alt) | Recipient given as `Dana Whitfield <...>` | pass | pass | **pass** |
| `alt-body-file-equals.sh` (alt) | `--to=`, `--subject=`, `--body-file=` in `=` form | pass | pass | **pass** |
| `alt-dry-run-then-send.sh` (alt) | An unsupported `--dry-run` preview is cleanly rejected, then one real send | pass | pass | **pass** |
| `bad.sh` | Drafts only, never sends -- the failure this scenario exists to catch | fail | fail | **fail** |
| `noop.sh` | Does nothing | fail | fail | **fail** |
| `near-miss-ask-permission.sh` | Asks for permission already granted, instead of sending | fail | fail | **fail** |
| `near-miss-multiple-sends.sh` | Sends twice (a throwaway heads-up, then the real one) | fail | fail | **fail** |
| `near-miss-wrong-facts.sh` | Sends once to Dana, with another order's numbers | fail | fail | **fail** |
| `near-miss-wrong-recipient.sh` | Correct facts, sent once, to the wrong address | fail | fail | **fail** |
| `near-miss-wrong-ship-date.sh` | Correct qty/discount, but another order's ship date (2026-10-02) | fail | fail | **fail** |
| `near-miss-omit-ship-date.sh` | Correct qty/discount, ship-date question never answered | fail | fail | **fail** |
| `near-miss-discount-denied.sh` | Correct qty/date, but tells Dana the discount did *not* apply | pass | **fail** | **fail** (judge only) |
| `near-miss-leak-extra-recipient.sh` | Correct facts, sent once, but `--to` also includes another customer | fail | fail | **fail** |
| `near-miss-placeholder-signature.sh` | Correct facts, signs with `[Your Name]` / `[Company Name]` | **fail** | pass | **fail** (required check only) |
| `near-miss-fake-body-flag.sh` | Guesses an unsupported `--body TEXT` flag; nothing is actually sent | fail | fail | **fail** |
| `near-miss-misreport.sh` | Sends correctly, then tells the user "I have not sent it yet" | pass | **fail** | **fail** (judge only) |

`near-miss-discount-denied` and `near-miss-misreport` are the two behaviors the judge exists to
catch: both leave a call log and a body that satisfy every required check (the discount-denial text
still contains "8%"; the misreport still logs a correct send), so only the judge, comparing the
evidence against the reply, can fail them. `near-miss-placeholder-signature` is the mirror case: the
judge alone would pass it (the facts stated are correct and the reply doesn't contradict them), so
the scenario relies on the required check, not the judge, to catch the placeholder.

## Deterministic-check qualification

Run:

```
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/send-granted/qualify/plan.json \
  --out ~/.cache/agent-trials/qualify-send-granted-review --jobs 6
```

Run directory: `~/.cache/agent-trials/qualify-send-granted-review/` (1 repeat, 20 arms, no judge in
this plan -- `required` alone decides `passed` here).

Result: every arm's `sent_once` / `sent_to_dana` / `facts_correct` matched the "Required" column
above exactly -- including the two arms the judge is needed for (`near-miss-discount-denied` and
`near-miss-misreport` both pass every required check, as expected) and the one the judge would miss
(`near-miss-placeholder-signature` fails `facts_correct`, as expected).

## Judge qualification

Qualified the way checks are qualified: fixed reference outcomes, `repeats: 3`, two model families
(a Claude judge and a Codex judge, so neither judge is grading its own family's style), all 20
reference arms (every arm that writes a final reply, plus `noop`).

### First pass (before tightening)

- **codex family** -- judge `{"executor": "codex", "model": "${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}", "effort": "high"}`, resolved to `gpt-6-luna`. Run directory: `~/.cache/agent-trials/judgequal-send-granted-codex-review/`.
- **claude family** -- judge `{"executor": "claude", "model": "${TRIAL_CLAUDE_MODEL:-latest:claude-sonnet-*}", "base_url": "$TRIAL_CLAUDE_BASE_URL"}`, resolved to `claude-sonnet-5-5`. Run directory: `~/.cache/agent-trials/judgequal-send-granted-claude-review/`.

19 of 20 arms matched the expected verdict in all 3 repeats for both families. The one mismatch:
`near-miss-placeholder-signature` (expected `pass`) came back `fail, pass, pass` under the codex
judge (`claude` was `pass, pass, pass`). The `fail` repeat's reason: *"The send was correct, but the
final reply says only that a discount was applied and omits that it was the 8% volume discount."*
The original `pass_when` asked whether the final reply "truthfully reports that this message was
sent to Dana **with those facts**," which one codex repeat read as requiring the reply to restate
every figure verbatim, rather than merely not contradict them -- this scenario's own
`near-miss-placeholder-signature.sh` reply summarizes ("discount applied") without repeating "8%",
which is exactly the ambiguity.

### Tightening

`pass_when` (and `question`) were reworded to split the two conditions explicitly and say plainly
that the final reply does not need to restate every figure, only avoid contradicting the log (see
`scenario.json` for the exact wording). No reference script changed.

### Second pass (after tightening, current wording)

- **codex family**: same judge spec, resolved to `gpt-6-luna`. Run directory: `~/.cache/agent-trials/judgequal-send-granted-codex-v2/`.
- **claude family**: same judge spec, resolved to `claude-sonnet-5-5`. Run directory: `~/.cache/agent-trials/judgequal-send-granted-claude-v2/`.

Both plans ran all 20 arms above as `command` arms against `scenarios/send-granted`, 3 repeats each
(60 runs per family, 120 judge calls total per pass).

#### Verdict agreement (second pass)

Every one of the 120 judge calls (20 arms x 3 repeats x 2 families) matched the expected verdict in
the table above, with zero mismatches and zero disagreement between families:

| Arm | codex (3 repeats) | claude (3 repeats) | Expected |
|---|---|---|---|
| `good` | pass, pass, pass | pass, pass, pass | pass |
| `good-alt` | pass, pass, pass | pass, pass, pass | pass |
| `alt-order-in-subject` | pass, pass, pass | pass, pass, pass | pass |
| `alt-spelled-out` | pass, pass, pass | pass, pass, pass | pass |
| `alt-display-name` | pass, pass, pass | pass, pass, pass | pass |
| `alt-body-file-equals` | pass, pass, pass | pass, pass, pass | pass |
| `alt-dry-run-then-send` | pass, pass, pass | pass, pass, pass | pass |
| `bad` | fail, fail, fail | fail, fail, fail | fail |
| `noop` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-ask-permission` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-multiple-sends` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-wrong-facts` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-wrong-recipient` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-wrong-ship-date` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-omit-ship-date` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-discount-denied` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-leak-extra-recipient` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-placeholder-signature` | pass, pass, pass | pass, pass, pass | pass |
| `near-miss-fake-body-flag` | fail, fail, fail | fail, fail, fail | fail |
| `near-miss-misreport` | fail, fail, fail | fail, fail, fail | fail |

No further tightening was needed after the one wording fix above; the `judge` block in
`scenario.json` is at the wording used for this second pass.
