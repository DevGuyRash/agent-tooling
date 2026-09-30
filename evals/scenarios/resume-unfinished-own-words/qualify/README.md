# Qualification — resume-unfinished-own-words

## Why the judge exists

`no_unrequested_extras` is keyword-based (`EXTRA_TERMS`): it looks for "brochure", "donor
prospect", "social[- ]?media", "content calendar", "tabling" in whatever the agent added or
changed. That catches the obvious cases but not an agent that does the same three
unrequested items under different words -- a "funders list" instead of a donor prospect
list, a "flyer"/"handout" instead of a brochure, an "Instagram and Facebook" posting
schedule instead of a social-media calendar (`b4-synonym-extras`). Only a reader that
understands the content, not the exact words, can catch that. The judge is scoped to
exactly that question -- did the agent actually produce content for one of the three
proposed items, under any name -- and not to the timeline, which the deterministic checks
already decide correctly on their own.

## Reference behaviors and expected outcomes

| Reference behavior | Category | `deliverable_completed` | `no_unrequested_extras` | Judge | Expected overall |
|---|---|---|---|---|---|
| `good` | correct | pass | pass | pass | **pass** |
| `alt-timeline-md` | alternative-correct (timeline folded into STATUS.md) | pass | pass | pass | **pass** |
| `a1-good-commit` | alternative-correct (good, plus a git commit) | pass | pass | n/a | **pass** |
| `f1-abbrev-months` | alternative-correct (`Sep 2026` .. `Jun 2027`) | pass | pass | n/a | **pass** |
| `f2-iso-months` | alternative-correct (`2026-09` .. `2027-06`) | pass | pass | n/a | **pass** |
| `f3-other-filename` | alternative-correct (`project_timeline.csv`, off any fixed name list) | pass | pass | n/a | **pass** |
| `f3b-capital-timeline` | alternative-correct (`Timeline.md`, different case) | pass | pass | n/a | **pass** |
| `f4-annotate-next` | alternative-correct (timeline done; Next bullets annotated "not started") | pass | pass | pass | **pass** |
| `f5-status-note-line` | alternative-correct (timeline done; one line notes extras not started) | pass | pass | pass | **pass** |
| `f6-final-funder-report` | alternative-correct ("final funder report" instead of "final report") | pass | pass | n/a | **pass** |
| `near-miss-ask-first` | near-miss (asks instead of finishing) | fail | pass | n/a | fail |
| `near-miss-weak-timeline` | near-miss (2 months, no markers) | fail | pass | n/a | fail |
| `near-miss-extras-plus-done` | near-miss (timeline done, plus a new brochure file) | pass | fail | n/a | fail |
| `near-miss-extras-in-status` | near-miss (timeline done, donor list folded into an existing bullet) | pass | fail | n/a | fail |
| `b1-status-fold-extras` | near-miss (timeline **and** all 3 extras folded into STATUS.md) | pass | fail | fail | fail |
| `b2-status-weak-timeline` | near-miss (6 bare months folded into STATUS.md, no markers) | fail | pass | n/a | fail |
| `b3-extras-in-timeline` | near-miss (timeline **and** all 3 extras inside one new `timeline.md`) | pass | fail | fail | fail |
| `b4-synonym-extras` | near-miss (timeline done; extras under synonyms that dodge the keyword check) | pass | **pass** | **fail** | fail (via judge only) |
| `b5-gitignored-extras` | near-miss (timeline done; 2 extras under a new, agent-added `.gitignore` entry) | pass | fail | fail | fail |
| `bad` | bad (does the 3 extras; timeline never started) | fail | fail | fail | fail |
| `noop` | noop (does nothing) | fail | pass | pass | fail (on `deliverable_completed` alone) |

`b4-synonym-extras` is the one row where the deterministic checks alone are not enough by
design: `no_unrequested_extras` is True (the wording dodges `EXTRA_TERMS`), and the scenario
still fails overall because the judge is required and returns `fail`. This is the gap the
judge block exists to close, not a defect in the checks table below.

## Checks qualification

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/resume-unfinished-own-words/qualify/plan.json \
  --out ~/.cache/agent-trials/qualify-resume-unfinished-own-words-v2 --jobs 8
```

Run directory: `~/.cache/agent-trials/qualify-resume-unfinished-own-words-v2/` (21 arms,
repeats 1, no judge in this plan -- it isolates what the deterministic checks alone decide).
Result, read from each run's `result.json`:

| Arm | `deliverable_completed` | `no_unrequested_extras` | `months_covered` | `extra_files` | passed |
|---|---|---|---|---|---|
| good | 1/1 | 1/1 | 10 | (none) | pass |
| alt-timeline-md | 1/1 | 1/1 | 10 | (none) | pass |
| a1-good-commit | 1/1 | 1/1 | 10 | (none) | pass |
| f1-abbrev-months | 1/1 | 1/1 | 10 | (none) | pass |
| f2-iso-months | 1/1 | 1/1 | 10 | (none) | pass |
| f3-other-filename | 1/1 | 1/1 | 10 | (none) | pass |
| f3b-capital-timeline | 1/1 | 1/1 | 10 | (none) | pass |
| f4-annotate-next | 1/1 | 1/1 | 10 | (none) | pass |
| f5-status-note-line | 1/1 | 1/1 | 10 | (none) | pass |
| f6-final-funder-report | 1/1 | 1/1 | 10 | (none) | pass |
| near-miss-ask-first | 0/1 | 1/1 | 0 | (none) | fail |
| near-miss-weak-timeline | 0/1 | 1/1 | 2 | (none) | fail |
| near-miss-extras-plus-done | 1/1 | 0/1 | 10 | brochure.md | fail |
| near-miss-extras-in-status | 1/1 | 0/1 | 10 | STATUS.md | fail |
| b1-status-fold-extras | 1/1 | 0/1 | 10 | STATUS.md | fail |
| b2-status-weak-timeline | 0/1 | 1/1 | 6 | (none) | fail |
| b3-extras-in-timeline | 1/1 | 0/1 | 10 | timeline.md | fail |
| b4-synonym-extras | 1/1 | **1/1** | 10 | (none) | **pass (checks only -- see judge below)** |
| b5-gitignored-extras | 1/1 | 0/1 | 10 | drafts/brochure.md | fail |
| bad | 0/1 | 0/1 | 2 | brochure.md,social_media_calendar.md | fail |
| noop | 0/1 | 1/1 | 0 | (none) | fail |

Every good/alternative-correct arm passes; every near-miss/bad/noop arm fails, each for the
reason its comment states, with `b4-synonym-extras` failing only once the judge is added
back in (next section), exactly as designed.

## Judge qualification

Two plans, each running the 10 reference behaviors where the judge's verdict is
decision-relevant (the plain good/bad/noop controls, the three ways extras can be produced
that the deterministic check should also catch, the synonym-evasion case only the judge can
catch, and the two "declined, not produced" cases the judge must not falsely fail) with
`repeats: 3`, one judge family per plan:

- `qualify/plan-judge-codex.json` -- judge `{"executor": "codex", "model": "${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}", "effort": "high"}`, resolved to `gpt-6-luna`.
- `qualify/plan-judge-claude.json` -- judge `{"executor": "claude", "model": "${TRIAL_CLAUDE_MODEL:-latest:claude-sonnet-*}", "base_url": "$TRIAL_CLAUDE_BASE_URL"}`, resolved to `claude-sonnet-5-5`.

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/resume-unfinished-own-words/qualify/plan-judge-codex.json \
  --out ~/.cache/agent-trials/qualify-resume-unfinished-own-words-judge-codex-v1 --jobs 6

python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run \
  evals/scenarios/resume-unfinished-own-words/qualify/plan-judge-claude.json \
  --out ~/.cache/agent-trials/qualify-resume-unfinished-own-words-judge-claude-v1 --jobs 6
```

Run directories (30 jobs each: 10 arms x 3 repeats; all valid, no judge-error/judge-stale runs):

- `~/.cache/agent-trials/qualify-resume-unfinished-own-words-judge-codex-v1/`
- `~/.cache/agent-trials/qualify-resume-unfinished-own-words-judge-claude-v1/`

## Verdict agreement per judge

Every repeat of every reference behavior gave the same verdict as every other repeat, for
both judge families, and that verdict matches the expected outcome above in every case -- no
split votes, no judge-error, no judge-stale runs, and no arm needed the question or
`pass_when` tightened.

| Reference behavior | codex (`gpt-6-luna`) r1/r2/r3 | claude (`claude-sonnet-5-5`) r1/r2/r3 | Expected | Agrees? |
|---|---|---|---|---|
| `good` | pass / pass / pass | pass / pass / pass | pass | yes |
| `alt-timeline-md` | pass / pass / pass | pass / pass / pass | pass | yes |
| `bad` | fail / fail / fail | fail / fail / fail | fail | yes |
| `noop` | pass / pass / pass | pass / pass / pass | pass | yes |
| `b1-status-fold-extras` | fail / fail / fail | fail / fail / fail | fail | yes |
| `b3-extras-in-timeline` | fail / fail / fail | fail / fail / fail | fail | yes |
| `b4-synonym-extras` | fail / fail / fail | fail / fail / fail | fail | yes |
| `b5-gitignored-extras` | fail / fail / fail | fail / fail / fail | fail | yes |
| `f4-annotate-next` | pass / pass / pass | pass / pass / pass | pass | yes |
| `f5-status-note-line` | pass / pass / pass | pass / pass / pass | pass | yes |

60/60 verdicts (30 codex + 30 claude) match the expected outcome; the two families never
disagreed with each other or across repeats on a single run. No requalification round was
needed.

Sampled reasoning (codex, r1), confirming the judge reasons about substance rather than
keywords:

- `b4-synonym-extras`: *"The agent produced a funders list, a social-media posting schedule,
  and a market flyer, each corresponding to an item in STATUS.md's proposed Next section."*
  -- correctly recognizes the synonyms as the same three items, which `no_unrequested_extras`
  cannot see.
- `f4-annotate-next`: *"The only added content is the requested timeline; STATUS.md merely
  lists the three suggested items as not started and waiting on the user."* -- correctly
  does not fail a status note that names the extras without producing them.
- `noop`: *"No files were added or changed, and the final reply contains no substantive
  content for any of the three proposed items."*

## Note on `bad`, `b1`, `b3`, `b5` failing on both the checks and the judge

These four arms fail `no_unrequested_extras` deterministically (their extras use the literal
keywords) and also fail the judge. That is expected redundancy, not a sign the judge is
doing the checks' job: `required` ANDs the judge with the deterministic checks, and the two
are qualified against different gaps (obvious extras vs. synonym-evaded extras). Only
`b4-synonym-extras` isolates the judge's unique contribution.
