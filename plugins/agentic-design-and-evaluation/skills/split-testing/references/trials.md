# Trial runtime

`scripts/trial.py` runs every alternative (an arm) on every scenario a set number of times, each run in its own fresh home and working directory, in an interleaved order, and summarizes pass counts with 95% Wilson intervals. You write the plan and scenarios for the question; the runtime owns isolation, confinement, repetition, the per-run record, blind judging, and aggregation.

```bash
python3 <skills-file-root>/scripts/trial.py run PLAN.json [--jobs 6] [--repeats 5] [--only s1,s2] [--arms a,b]
python3 <skills-file-root>/scripts/trial.py summarize RUN_DIR
```

Runs land under `~/.cache/agent-trials/<plan>-<timestamp>/` by default; the runtime refuses an output directory inside a git repository, because executors would otherwise pick up that repository's instructions. Rerunning with the same `--out` reuses finished runs and replaces partial ones.

## Plan

```json
{"name": "kernel-screen", "repeats": 5, "seed": 1,
 "arms": {"none":   {"executor": "codex", "model": "gpt-6-luna", "effort": "high"},
          "kernel": {"executor": "codex", "model": "gpt-6-luna", "effort": "high",
                     "instructions": "arms/kernel.md"},
          "kernel-claude": {"executor": "claude", "model": "claude-sonnet-5",
                            "base_url": "https://proxy.example", "instructions": "arms/kernel.md"}},
 "judge": {"executor": "codex", "model": "gpt-6-luna", "effort": "high"},
 "scenarios": ["scenarios/gate-deploy", "scenarios/pr-no-merge"]}
```

Paths are relative to the plan; `~` expands. An arm's `instructions` file becomes the executor's user-level instructions (Codex `AGENTS.md` in a private `CODEX_HOME`; Claude appended system prompt in `--bare` mode). Executors:

- `codex`: `codex exec` with only the user's model provider settings copied into a private home, so no plugins, skills, memories, or user instructions load beyond the arm's. The provider credential file is sourced into the child process only.
- `claude`: `claude -p --bare`, which skips hooks, plugins, memory, and CLAUDE.md discovery and authenticates only through an API key, never OAuth. With `"base_url"` set to an Anthropic-compatible endpoint (such as a model proxy), the key comes from `"api_key_var"` in the env file (default: the Codex provider's key variable), the run is confined like codex runs with its own HOME, and permission prompts are bypassed inside the sandbox; without `base_url`, `ANTHROPIC_API_KEY` must already be set. The plan's `judge` accepts the same `executor`, `model`, and `base_url` settings.
- `command`: a shell command, for non-agent comparisons (scripts, builds, tools) and for qualifying checks. It receives `TRIAL_PROMPT`, `TRIAL_SCENARIO_DIR`, `TRIAL_JOB_DIR`, and `TRIAL_INSTRUCTIONS` (the arm's instructions file, if any).

## Scenario

```
scenario.json   {"prompt": "...", "followups": ["continue"], "timeout_s": 900,
                 "required": ["check_a", "check_b"], "bin": ["../_shared/bin"],
                 "judge": {"question": "...", "pass_when": "..."}}
fixture/        copied into the working directory
setup.sh        runs in the working directory first (for example, to create a repo and a local origin)
bin/            fake tools, copied into the run and first on PATH; they may append JSON lines to $TRIAL_HARNESS/calls.jsonl
check.py        def check(run) -> {name: bool | number | str}; optional def judge_context(run) -> str
qualify/        good.sh and bad.sh reference behaviors for qualifying the checks
```

A run passes when the executor finished, every `required` check is `True`, and the judge (when the scenario and plan both define one) says `pass`. Numbers and strings are reported as measures without deciding the pass. `followups` continue the same conversation, which is how a scenario reproduces a user sending "continue".

`check(run)` sees the resulting state and the native record: `run.workdir`, `run.harness`, `run.final_message`, `run.messages`, `run.commands`, `run.calls` (fake-tool log), `run.usage`, `run.git(...)` and `run.git_rc(...)`, `run.file(rel)` and `run.read(path)`, `run.copy_workdir()`, and `run.sandboxed(cmd, cwd=..., timeout=...)`. Prefer checks on state (files, commits, remotes, tool calls) over checks on wording.

The agent controls its repository's configuration, the links in its files, and its code, so a check reads and runs them only through these: `run.git` overrides git settings that run commands and runs git confined and read-only; `run.file` and `run.read` return nothing for a path that resolves outside the run directory; `run.sandboxed` runs agent-written code with no network, the host read-only, the user's home hidden, and its own process namespace, typically on `run.copy_workdir()` so the working directory stays as the agent left it.

## Confinement

By default (`"sandbox": "confined"`) codex, command, and proxied claude runs execute inside bubblewrap: the host is read-only, the user's home is hidden, only the run directory is writable, and everything the agent starts lives in its own process namespace and ends with the run; Codex's own sandbox is off inside it so agents can commit. Judges run the same way. The provider key is read from its credential file outside the sandbox and only that one variable is passed in, so the file itself stays hidden; the executor, and tool processes it does not filter, can still see the key in its environment. The environment is rebuilt from system paths with a throwaway `HOME`, git configuration, and gh configuration, no SSH agent, and no tokens, so agents reach only the scenario's fake tools. Setting `sandbox` to a Codex sandbox mode uses that instead.

## Qualifying checks

Before relying on a scenario, run its reference behaviors with the `command` executor:

```json
{"name": "qualify", "repeats": 1,
 "arms": {"good": {"executor": "command", "command": "sh \"$TRIAL_SCENARIO_DIR/qualify/good.sh\""},
          "bad":  {"executor": "command", "command": "sh \"$TRIAL_SCENARIO_DIR/qualify/bad.sh\""}},
 "scenarios": ["scenarios/gate-deploy"]}
```

The good behavior must pass and the bad one must fail. A check that only an agent can trigger (for example, one that reads agent command events) is qualified on agent runs instead.

## Two-stage trials

When the question is whether what an agent writes works for the agent that later follows it (a skill, a brief, a repaired instruction), judge the artifact by its consumer, not by reading it. After the authoring run:

```bash
python3 <skills-file-root>/scripts/trial.py derive RUN_DIR --scenario repair-ask-first-skill \
  --artifact skills/deploy-helper/SKILL.md --consumer scenarios/use-deploy-skill \
  --executor '{"executor": "codex", "model": "gpt-6-luna", "effort": "high"}' --repeats 2 --plan consumer.json
python3 <skills-file-root>/scripts/trial.py run consumer.json
python3 <skills-file-root>/scripts/trial.py summarize CONSUMER_RUN_DIR --group
```

Each produced artifact becomes an arm named `<authoring arm>~r<repeat>`; `--group` pools them back into their authoring arm.

## Re-scoring stored runs

After a check changes, `trial.py recheck RUN_DIR` re-scores finished runs without running any agent again and keeps their stored verdicts; `--rejudge` also asks the plan's judge again with the scenario's current question and evidence, and `--judge JSON` does so with a different judge; `--only s1,s2` limits either to those scenarios. A judge decides runs the checks cannot, so qualify it the way checks are qualified: fixed reference outcomes (the same state with different replies, for example), each judged several times, where the expected verdict is known. A judge from another model family than the executors guards against a judge that favors its own family's style.

## Reading results

`summary.md` lists passed / valid runs per scenario and arm with intervals, per-arm cost (output tokens, commands, seconds), and each check's rate. Invalid runs (timeouts, executor errors, broken checks) are listed separately and never counted as failures of the arm; `--retry-invalid` reruns them, and transport failures are retried automatically. Each run's host caches (such as a Codex plugin catalog) are pruned when it finishes, and the runtime stops scheduling when free space falls below `TRIAL_MIN_FREE_GB` (default 5). Each run directory keeps `events.jsonl`, the final messages, the executor's own session files (the exact instructions it received), `calls.jsonl`, the judge's prompt and verdict, and `result.json`.

Nine cases run five times each are nine cases, not forty-five: judge generalization by the number of distinct scenarios, and keep a few scenarios out of development so they can test whether a change generalizes.
