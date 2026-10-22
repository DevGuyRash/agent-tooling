# Launchers for this repository's evals

The Split Testing runtime starts no executor of its own: a plan's launcher arm names a script that starts one, under the contract in `plugins/agentic-design-and-evaluation/skills/split-testing/references/launching.md`. These are the launchers this repository's maintainers use for the two agent command lines they run, kept here as eval data. They are examples of the contract, not part of the skill, and anyone with another executor writes their own.

- `codex.py`: Codex CLI. Setup keeps only the model provider block of this machine's Codex configuration (copied in with `"copy": {".launcher/host-codex.toml": "~/.codex/config.toml"}` and deleted before the agent starts) and writes the arm's instructions as `AGENTS.md`; each turn runs `codex exec`, then `codex exec resume`. As a judge it runs read-only with the schema as its output schema.
- `claude.py`: Claude Code. Each turn runs `claude -p` in bare mode with the instructions appended to the system prompt, resuming the first turn's session. A resource at `~/.launcher/settings.json` with `{"bare": false}` (`claude-discovery.json` here) turns on skill discovery for selection trials (hide `/etc/claude-code` with the arm's `"hide"`). As a judge it runs with no tools and the schema as its JSON schema.

Both convert the executor's own event stream and session files into the trial record: actions in the order they started, with their outcomes and output (a subagent's actions carry its `agent`: a Codex subagent's come from its own rollout, and a Claude subagent's that only its transcript holds from that transcript, each placed among the main agent's actions by the times those records give), usage in the shared vocabulary (Codex reports running totals, so its last turn's count; Claude reports per turn, with cache reads and writes outside `input_tokens`, so its turns are summed with those added back), the session and model each turn reports, and the skill listing where the executor's record shows one.

The Codex record claims coverage only where its native evidence supports completeness. Missing output is not an empty output, and missing outcomes, truncation, opaque calls, incomplete turns or missing agent rollouts withdraw the affected coverage and appear in `limits`. Visible skill content and injected loads still establish positive skill-selection evidence; without such evidence, incomplete coverage means unknown, not that a skill was never read. An explicitly captured empty command output remains known empty. Injected loads retain their content for the consumer's stricter resource-exposure checks; command output alone does not prove which resource revision was read. Native records are retained for inspection; these conversions do not recover evidence the executor did not record.

An arm names the executable and its key variable, for example:

```json
{"executor": "launcher", "script": "../launchers/codex.py", "binary": "${TRIAL_CODEX_BIN:-codex}",
 "model": "${TRIAL_CODEX_MODEL:-gpt-6.1-sol}", "api_key_var": "${TRIAL_CODEX_KEY_VAR:-OPENAI_API_KEY}",
 "copy": {".launcher/host-codex.toml": "~/.codex/config.toml"}}
```

`tests/test_launchers.py` checks both conversions on hand-written events in each executor's format, with expected values worked out by hand.

