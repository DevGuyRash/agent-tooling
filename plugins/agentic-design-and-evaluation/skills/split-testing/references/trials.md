# Trial runtime

`scripts/trial.py` runs every alternative (an arm) on every scenario a set number of times, each run in its own fresh home and working directory, in an interleaved order, and summarizes pass counts with 95% Wilson intervals. You write the plan and scenarios for the question; the runtime owns isolation, confinement, repetition, the per-run record, blind judging, and aggregation.

```bash
python3 <skills-file-root>/scripts/trial.py run PLAN.json [--jobs 6] [--repeats 5] [--only s1,s2] [--arms a,b]
python3 <skills-file-root>/scripts/trial.py summarize RUN_DIR
python3 <skills-file-root>/scripts/trial.py models [--match 'claude-sonnet-*'] [--latest] [--base-url URL] [--env-file F] [--api-key-var V]
```

Runs land under `~/.cache/agent-trials/<plan>-<timestamp>/` by default; the runtime refuses an output directory inside a git repository, because executors would otherwise pick up that repository's instructions. Rerunning with the same `--out` reuses finished runs and replaces partial ones. Every run records its arm's executor, model, effort, `base_url`, instructions digest, command, `allowed_tools`, and `permission_mode` (executors read a copy of the instructions kept in the run directory, so the digest is what every run received), and the judge that scored it (executor, model, effort, `base_url`); a rerun whose arm or judge differs from those records is refused, so one run directory never mixes models, instructions, or judges. Other settings, CLI versions, and scenario content are not compared. One `run` or `recheck` uses a directory at a time.

## Plan

```json
{"name": "kernel-screen", "repeats": 5, "seed": 1,
 "arms": {"none":   {"executor": "codex", "model": "${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}", "effort": "high"},
          "kernel": {"executor": "codex", "model": "${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}", "effort": "high",
                     "instructions": "arms/kernel.md"},
          "kernel-claude": {"executor": "claude", "model": "${TRIAL_CLAUDE_MODEL:-latest:claude-sonnet-*}",
                            "base_url": "https://proxy.example", "instructions": "arms/kernel.md"}},
 "judge": {"executor": "codex", "model": "gpt-6-luna", "effort": "high"},
 "scenarios": ["scenarios/gate-deploy", "scenarios/pr-no-merge"]}
```

The settings fields `model`, `effort`, `base_url`, `binary`, `env_file`, and `api_key_var` of arms and the judge expand `${VAR}` and `${VAR:-default}` (without nesting; a command arm's `command` does not expand, because its `$TRIAL_*` variables belong to its shell), and a field other than `model` that expands to nothing is unset (an empty `model` is an error). Expanded values are recorded verbatim in the run directory, in `plan.json` and in each run's `result.json`, and can appear in error messages, so a key belongs only behind `env_file` and `api_key_var`. A model `latest:GLOB` resolves to the newest model the endpoint serves in which each `*` (at most three) is a version number (`5-5`, `6.1`; from a date stamp of four or more digits on, a version only breaks ties): `latest:claude-sonnet-*` picks the newest Sonnet and never a variant such as `-thinking`, and `latest:gpt-*` picks the newest suffix-less `gpt-N` (`gpt-5.5`, never `gpt-6-luna`), so a family is named by its suffix, as in `latest:gpt-*-luna`. A Claude arm's models are listed at its `base_url` (Anthropic format), any other arm's at the Codex model provider (OpenAI format), with the provider key from `codex.env` unless `env_file` and `api_key_var` name another; the key never follows a redirect, and an endpoint URL carrying credentials, a query, or a fragment is refused. `trial.py models` lists what an endpoint serves (`--latest` shows what `latest:MATCH` resolves to), and `TRIAL_MODELS_FILE` (one ID per line) replaces the query. A run directory resolves each spec once and keeps every resolution in `plan.json` (an arm records the spec as written as `model_spec` and the expanded `latest:` spec as `model_query`); a rerun, or an arm added later with the same spec and endpoint, takes the recorded model, while a new directory gets the newest. `--dry-run` asks no endpoint and shows a spec the directory has not resolved as unresolved, unless `TRIAL_MODELS_FILE` answers it. Name an exact model when a comparison must stay reproducible across run directories.

Scenario, `instructions`, and `env_file` paths are relative to the plan; `~` expands. An arm's `instructions` file becomes the executor's user-level instructions (Codex `AGENTS.md` in a private `CODEX_HOME`; Claude appended system prompt in `--bare` mode). Executors:

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

The agent controls its repository's configuration, the links in its files, and its code, so a check reads and runs them only through these: `run.git` overrides git settings that run commands and runs git confined and read-only; `run.file` and `run.read` return nothing for a path that resolves outside the run directory; `run.sandboxed` runs agent-written code with no network, the host read-only, the user's home hidden, and its own process namespace, typically on `run.copy_workdir()` so the working directory stays as the agent left it (the copy is empty when the agent replaced the working directory itself with a link).

## Confinement

By default (`"sandbox": "confined"`) codex, command, and proxied claude runs execute inside bubblewrap: the host is read-only, the user's home is hidden, only the run directory is writable, and everything the agent starts lives in its own process namespace and ends with the run; Codex's own sandbox is off inside it so agents can commit. Judges run the same way. The provider key is read from its credential file outside the sandbox and only that one variable is passed in, so the file itself stays hidden; the executor, and tool processes it does not filter, can still see the key in its environment. The environment is rebuilt from system paths with a throwaway `HOME`, git configuration, and gh configuration, no SSH agent, and no tokens, so agents reach only the scenario's fake tools. After a run the runtime writes, reads, and prunes the run directory without following a link or waiting on a special file the agent left there, so what the agent planted cannot reach the host; `derive` copies an artifact only when it is a regular file inside that run's own working directory. Setting `sandbox` to a Codex sandbox mode uses that instead.

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

Each produced artifact becomes an arm named `<authoring arm>~r<repeat>`; `--group` pools them back into their authoring arm. Without `--executor` the arms use `${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}` at high effort, and a relative `env_file` in `--executor` is rewritten relative to the derived plan.

## Re-scoring stored runs

After a check changes, `trial.py recheck RUN_DIR` re-scores finished runs without running any agent again and keeps their stored verdicts; `--rejudge` also asks the plan's judge again with the scenario's current question and evidence, and `--judge JSON` does so with a different judge, which becomes the directory's judge: it re-judges every run the judge scores, refusing before it judges anything when the checks of one of them fail to run and changing nothing when the new judge gives no verdict for one of them, so `--only` cannot limit it while scenarios outside `--only` have finished runs with a judge question; `--only s1,s2` limits the others to those scenarios. A run whose verdict comes from another judge than the directory's (or that has none) does not score: `recheck` reports it as `judge-stale` until `--rejudge` judges it. A judge decides runs the checks cannot, so qualify it the way checks are qualified: fixed reference outcomes (the same state with different replies, for example), each judged several times, where the expected verdict is known. A judge from another model family than the executors guards against a judge that favors its own family's style.

## Reading results

`summary.md` lists passed / valid runs per scenario and arm with intervals, per-arm cost (output tokens, commands, seconds), and each check's rate. Invalid runs (timeouts, executor errors, broken checks, a judge that gave no verdict, a verdict from another judge than the directory's) are listed separately and never counted as failures of the arm; `--retry-invalid` reruns them, and transport failures are retried automatically. Each run's host caches (such as a Codex plugin catalog) are pruned when it finishes, and the runtime stops scheduling when free space falls below `TRIAL_MIN_FREE_GB` (default 5). Each run directory keeps `events.jsonl`, the final messages, the executor's own session files (the exact instructions it received), `calls.jsonl`, the judge's prompt and verdict, and `result.json`.

Nine cases run five times each are nine cases, not forty-five: judge generalization by the number of distinct scenarios, and keep a few scenarios out of development so they can test whether a change generalizes.
