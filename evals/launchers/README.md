# Launchers for this repository's evals

The Split Testing runtime starts no executor of its own: a plan's launcher arm names a script that starts one, under the contract in `plugins/agentic-design-and-evaluation/skills/split-testing/references/launching.md`. These are the launchers this repository's maintainers use for the two agent command lines they run, kept here as eval data. They are examples of the contract, not part of the skill, and anyone with another executor writes their own.

- `codex.py`: Codex CLI. Setup keeps only the model provider block of this machine's Codex configuration (copied in with `"copy": {".launcher/host-codex.toml": "~/.codex/config.toml"}` and deleted before the agent starts) and writes the arm's instructions as `AGENTS.md`; each turn runs `codex exec`, then `codex exec resume`. Its private configuration also turns off every feature that would bring what a signed-in ChatGPT account holds into a run (`ACCOUNT_FEATURES_OFF`: `apps`, `plugins`, `remote_plugin`, `plugin_sharing`, `recommended_plugins`, `tool_suggest` and `memories`, as Codex's own feature table, `codex-rs/features/src/lib.rs`, names them). No control covers the account's identity or the policies its workspace delivers to business, education and enterprise plans (`codex-rs/cloud-config`), limits to state with the results. As a judge it runs read-only with the schema as its output schema.
- `claude.py`: Claude Code. Each turn runs `claude -p` in bare mode with the instructions appended to the system prompt, resuming the first turn's session. A resource at `~/.launcher/settings.json` with `{"bare": false}` (`claude-discovery.json` here) turns on skill discovery for selection trials (hide `/etc/claude-code` with the arm's `"hide"`). As a judge it runs with no tools and the schema as its JSON schema. In bare mode Claude Code signs in only with an API key (the arm's `api_key_var`); without it (`{"bare": false}`), it reads the sign-in the controller gives its home, its credential file through `copy` or a long-lived token passed by name, which also turns discovery on. A claude.ai login also brings that account into every run: its synced skills and plugins, its connectors (a claude.ai Docs connector with write tools, say), and its email and organization in Claude Code's own context. Without bare mode the launcher turns off everything Claude Code 2.1.299 offers a control for (`ACCOUNT_OFF`), with `--settings`, which layers over the run's own user settings and writes nothing (an arm's read-only `~/.claude/settings.json` resource stays as placed), and one environment variable:

  | Control | What it turns off | Source |
  | --- | --- | --- |
  | `syncClaudeAiSkills: false` | the account's synced skills | settings reference |
  | `syncClaudeAiPlugins: false` | the account's synced plugins | settings reference |
  | `disableClaudeAiConnectors: true`, `ENABLE_CLAUDEAI_MCP_SERVERS=false` | the account's claude.ai connectors | settings reference, environment variables |
  | `enableArtifact: false` | the Artifact tool, which publishes to the account's claude.ai | settings reference |
  | `autoMemoryEnabled: false` | memory: the organization's memory stores load only with auto memory on, so the run's own auto memory goes too, as in bare mode | settings reference, binary |
  | `disableRemoteControl: true` | Remote Control of the run from the account's apps | settings reference |
  | `crossSessionInbound: "refuse"` | messages from the account's other sessions | settings reference |
  | `isolatePeerMachines: true` | messages to the account's sessions beyond this machine, which then need an approval the run has no one to give | settings reference |
  | `autoUploadSessions: false` | mirroring the run to claude.ai | the binary's settings schema |
  | `permissions.deny`: `RemoteTrigger`, `DesignSync`, `ShareOnboardingGuide` | the tools that write to the account (its cloud scheduled tasks, its claude.ai/design projects, a shared onboarding guide), each removed whole by a bare-name deny rule | permissions, tools reference, the binary |

  "Settings reference", "environment variables", "tools reference" and "permissions" are the pages under code.claude.com/docs/en/ of those names. No control covers the account's identity (its email in Claude Code's own context, its organization in the transcript) or the settings its organization delivers (server-managed settings, which outrank every local source), limits to state with the results.

Both convert the executor's own event stream and session files into the trial record: actions in the order they started, with their outcomes and output (a subagent's actions carry its `agent`: a Codex subagent's come from its own rollout, and a Claude subagent's that only its transcript holds from that transcript, each placed among the main agent's actions by the times those records give), usage in the shared vocabulary (Codex reports running totals, so its last turn's count; Claude reports per turn, with cache reads and writes outside `input_tokens`, so its turns are summed with those added back), the session and model each turn reports, and the skill listing where the executor's record shows one.

The Codex record claims coverage only where its native evidence supports completeness. Missing output is not an empty output, and missing outcomes, truncation, opaque calls, incomplete turns or missing agent rollouts withdraw the affected coverage and appear in `limits`. Visible skill content and injected loads still establish positive skill-selection evidence; without such evidence, incomplete coverage means unknown, not that a skill was never read. An explicitly captured empty command output remains known empty. Injected loads retain their content for the consumer's stricter resource-exposure checks; command output alone does not prove which resource revision was read. Native records are retained for inspection; these conversions do not recover evidence the executor did not record.

An arm names the executable and its key variable, for example:

```json
{"executor": "launcher", "script": "../launchers/codex.py", "binary": "${TRIAL_CODEX_BIN:-codex}",
 "model": "${TRIAL_CODEX_MODEL:-gpt-6.1-sol}", "api_key_var": "${TRIAL_CODEX_KEY_VAR:-OPENAI_API_KEY}",
 "copy": {".launcher/host-codex.toml": "~/.codex/config.toml"}}
```

`tests/test_launchers.py` checks both conversions on hand-written events in each executor's format, with expected values worked out by hand.

