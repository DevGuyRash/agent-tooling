# Trial: candidate review instructions

**Question.** Should the review bot switch from `instructions/current.md` to `instructions/candidate.md`? The candidate says the same things in about 40% fewer words, which cuts the prompt cost of every review.

**Arms.** `incumbent` = `instructions/current.md`, `candidate` = `instructions/candidate.md`.

**Scenarios.** 10 seeded pull requests, each with one planted problem the review must block on (an inline comment on the right line naming the problem, and "Request changes"):

| Scenario | Planted problem |
|---|---|
| `raw-sql-in-orm` | f-string SQL in a raw ORM query |
| `cache-invalidation-race` | cache cleared before the write commits |
| `null-deref-on-retry` | retry path dereferences a value that is None after a timeout |
| `public-api-rename` | public client method renamed with no alias |
| `secret-in-fixture` | live-looking API key in a test fixture |
| `n-plus-one-query` | query per item inside a loop |
| `pagination-off-by-one` | last page skipped |
| `unsafe-yaml-load` | `yaml.load` on request data |
| `sleep-in-test` | `time.sleep(2)` instead of waiting for a condition |
| `migration-without-down` | migration with no down step on a populated table |

**Hosts.** Each scenario runs on four agent hosts: `codex`, `claude-code`, `gemini-cli`, `opencode`.

**Repeats.** 6 runs per scenario per host per arm, so 240 reviews per arm. Runs are interleaved across arms, each in a fresh container.

**Grading.** A run passes when the grader finds the inline comment on the planted problem and the summary requests changes. Same grader and rubric as the shakedown runs.

**Output.** One file, `results.csv`, one row per scenario, host, and arm:

```
scenario,host,variant,repeats,passed
raw-sql-in-orm,codex,incumbent,6,5
raw-sql-in-orm,codex,candidate,6,6
...
```

80 data rows: 10 scenarios x 4 hosts x 2 arms. `passed` is out of `repeats`.

**Decision rule.** `trial/decide.py`, written before the trial runs. Usage: `python3 trial/decide.py results.csv` from the repository root; prints `adopt`, `reject`, or `inconclusive`.
