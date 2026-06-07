# Goal Foundry Plugin

Goal Foundry is a Codex and Claude plugin package that turns messy intent,
broad project context, PRDs, logs, issues, and existing goal notes into
bounded, verifiable goal contracts.

Doctrine:

> Open-world discovery. Closed-world execution.

Goal Foundry is designed to be used with a bounded execution loop, not instead
of one. It creates or validates `.goals/current.md`, renders a paste-ready goal
objective, inventories existing capabilities, captures evidence, protects
frozen goal artifacts, and audits completed runs.

## What this package contains

```text
goal-foundry/
  .codex-plugin/plugin.json              Codex plugin manifest
  .claude-plugin/plugin.json             Claude plugin manifest
  skills/authoring-goals/SKILL.md        primary skill, invoked as $authoring-goals
  skills/authoring-goals/agents/         Codex skill UI/invocation metadata
  skills/authoring-goals/references/     doctrine, schema, rubric, examples
  skills/authoring-goals/assets/         templates, AGENTS snippet, custom-agent templates
  skills/authoring-goals/scripts/        deterministic helpers and wrapper CLI
  hooks/hooks.json                       lifecycle hook bundle
  hooks/scripts/                         prompt/scope/evidence/stop guard hooks
  examples/                              sample inputs, contracts, registries, reports
  tests/                                 fast smoke test
```

The final form is a **plugin**. Its core is one primary **skill**
(`$authoring-goals`) because skill metadata/instructions are the right home for
the judgment workflow, while the plugin container bundles hooks, scripts,
metadata, and assets.

## Marketplace layout

This repository keeps plugin packages under top-level `plugins/` and publishes
host marketplace files at the repo root:

- Codex: `.agents/plugins/marketplace.json`
- Claude: `.claude-plugin/marketplace.json`

WHEN installing this package from this repository THEN you SHALL use the
marketplace manifest for the target host.

## Install locally

For a different repository, copy this plugin folder into that repository's
`plugins/` directory:

   ```bash
   mkdir -p plugins
   cp -R /absolute/path/to/goal-foundry ./plugins/goal-foundry
   ```

Add or update the target host marketplace.

Codex:

   ```json
   {
     "name": "local-goal-foundry",
     "interface": { "displayName": "Local Goal Foundry" },
     "plugins": [
       {
         "name": "goal-foundry",
         "source": { "source": "local", "path": "./plugins/goal-foundry" },
         "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
         "category": "Productivity"
       }
     ]
   }
   ```

Claude:

   ```json
   {
     "name": "local-goal-foundry",
     "owner": { "name": "Local Goal Foundry" },
     "plugins": [
       {
         "name": "goal-foundry",
         "source": "./plugins/goal-foundry",
         "description": "Compile messy intent into bounded goal contracts.",
         "version": "1.0.0"
       }
     ]
   }
   ```

Restart the target host, install/enable the plugin, and review/trust hooks using
the host's plugin and hook review flow.

## Initialize a project

After installing the plugin, initialize project artifacts from the repo root:

```bash
python3 plugins/goal-foundry/skills/authoring-goals/scripts/goal_foundry.py init --append-agents-md
```

Optional custom-agent templates for read-only discovery/audit can be installed into `.codex/agents/`:

```bash
python3 plugins/goal-foundry/skills/authoring-goals/scripts/goal_foundry.py init --install-agents
```

This creates:

```text
.goals/
  GOALS.md                  registry/backlog, not execution target
  current.template.md       starter contract template
  graph.json                relationship/status graph
  frontier.md               discovery frontier report
  evidence/                 raw verifier/tool evidence
  reports/                  run/audit reports
  AGENTS.goal-foundry.snippet.md
```

## Use with Codex `/goal`

Invoke the skill explicitly:

```text
Use $authoring-goals to compile this raw request into .goals/current.md and a paste-ready /goal:
"Improve auth tests."
```

The skill should output:

```text
- Mode
- Launchability verdict
- Forever-risk score
- Capability summary
- Missing or assumed fields
- Artifact decision
- .goals/current.md content, when one goal is selected
- validation/lock command
- paste-ready /goal objective
- optional GOALS.md or graph update
```

Then lock and render the current contract:

```bash
python3 plugins/goal-foundry/skills/authoring-goals/scripts/goal_foundry.py validate .goals/current.md --write-hash
python3 plugins/goal-foundry/skills/authoring-goals/scripts/goal_foundry.py render .goals/current.md --write .goals/rendered-goal.txt
```

Run Codex `/goal` using the rendered objective.

## Capability inventory

Before non-trivial authoring/scanning/auditing, Goal Foundry inventories existing capabilities:

```bash
python3 plugins/goal-foundry/skills/authoring-goals/scripts/goal_foundry.py inventory --format markdown
```

It looks for:

- project/user skills
- local plugins and marketplace entries
- MCP server declarations in Codex config, plugin config, and `.mcp.json`
- custom agents under `.codex/agents` and user agents
- active hooks
- AGENTS.md guidance
- existing `.goals/` artifacts
- inferred project test/build/lint commands

Contracts should include only capabilities that are actually discovered, explicitly provided, or clearly inferable from local files.

## Contract freeze

`.goals/current.md` is the source of truth. Once validated, `validate_goal.py --write-hash` writes `.goals/current.sha256`. During a `/goal` run:

- the executor may read `.goals/current.md`
- the executor must not modify `.goals/current.md` or `.goals/current.sha256`
- allowed writes inside `.goals/` are limited to `.goals/evidence/` and `.goals/reports/`
- a hash mismatch is an audit failure

Hooks are guardrails, not a security sandbox. The audit script also checks contract hash integrity.

## Helper CLI

```bash
python3 skills/authoring-goals/scripts/goal_foundry.py init
python3 skills/authoring-goals/scripts/goal_foundry.py inventory --format markdown
python3 skills/authoring-goals/scripts/goal_foundry.py validate .goals/current.md --write-hash
python3 skills/authoring-goals/scripts/goal_foundry.py render .goals/current.md --write .goals/rendered-goal.txt
python3 skills/authoring-goals/scripts/goal_foundry.py risk "Improve the whole app"
python3 skills/authoring-goals/scripts/goal_foundry.py extract src tests docs --write .goals/candidates.md
python3 skills/authoring-goals/scripts/goal_foundry.py select
python3 skills/authoring-goals/scripts/goal_foundry.py graph --add-contract .goals/current.md
python3 skills/authoring-goals/scripts/goal_foundry.py ledger --current .goals/current.md --status active
python3 skills/authoring-goals/scripts/goal_foundry.py verifiers .goals/current.md
python3 skills/authoring-goals/scripts/goal_foundry.py audit .goals/current.md --report .goals/reports/latest.md
```

## Goal artifacts

```text
.goals/current.md      one active executable contract
.goals/GOALS.md        human-readable registry/backlog
.goals/graph.json      machine-readable relationships/statuses
.goals/frontier.md     what discovery looked at and did not look at
.goals/evidence/       raw verifier/tool evidence
.goals/reports/        final reports and audit reports
```

Never run `/goal` against `.goals/GOALS.md`. Compile one ready item into `.goals/current.md` first.

## Suggested AGENTS.md companion rule

A compact version is available at `skills/authoring-goals/assets/AGENTS.snippet.md`:

```markdown
## Goal Foundry rule

For long-running or autonomous work, do not start Codex `/goal` from a vague request directly. First use `$authoring-goals` to create or validate `.goals/current.md`. Run `/goal` only against one compiled current goal contract, never against `.goals/GOALS.md` or an open-ended backlog.
```

## Optional custom agents

Codex custom agents are project/user configuration. This plugin includes templates but does not auto-install them unless you run the initializer with `--install-agents`:

```text
skills/authoring-goals/assets/codex-agents/goal-discoverer.toml
skills/authoring-goals/assets/codex-agents/goal-auditor.toml
```

Use them for read-heavy scans and skeptical audits. They are not oracles; deterministic verifiers and evidence artifacts remain the source of truth.

## Test the package

```bash
bash tests/run_smoke_tests.sh
```

## Deliberate boundaries

- Goal Foundry does not automatically launch the next goal after closing one. The outer loop is human-stepped by default.
- Goal Foundry does not bundle MCP servers. It inventories and uses existing project/user MCP capabilities.
- Goal Foundry cannot make hooks a perfect sandbox. It combines hook guardrails, deterministic validation, contract hash checks, and audit.

## Official Codex docs to verify current behavior

- https://developers.openai.com/codex/plugins/build
- https://developers.openai.com/codex/skills
- https://developers.openai.com/codex/hooks
- https://developers.openai.com/codex/concepts/customization
- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/guides/agents-md
