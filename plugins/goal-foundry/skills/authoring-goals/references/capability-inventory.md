# Capability Inventory

Goal Foundry should query existing capabilities before compiling non-trivial goals.

## Why

Available skills, MCP servers, plugins, hooks, subagents, and project commands change what goals are safely launchable. For example:

- A GitHub MCP server can verify issue status.
- A Linear MCP server can read ticket requirements.
- A browser/Figma MCP server can verify UI context.
- Existing test scripts can become stronger verifiers.
- Existing hooks may already enforce style or scope.
- Existing skills may perform domain-specific analysis.

## Required behavior

1. Run or emulate `inventory_capabilities.py`.
2. Include a short inventory summary in the response.
3. Add relevant capabilities to the `Available Capabilities` section of `.goals/current.md`.
4. Prefer existing capabilities over invented or manual steps.
5. Do not require capabilities that are not discovered or explicitly provided.
6. If capability inventory fails, document that fact and make conservative assumptions.

## What to look for

- `.agents/skills/**/SKILL.md`
- user skills under `~/.agents/skills` and `~/.codex/skills` when readable
- `.agents/plugins/marketplace.json`
- `~/.agents/plugins/marketplace.json`
- plugin manifests under local plugin directories and `~/.codex/plugins/cache`
- `.mcp.json` files
- `[mcp_servers.*]` declarations in `~/.codex/config.toml`, `.codex/config.toml`, and discovered config files
- `hooks.json` and inline hooks in config files
- `agents/openai.yaml`, subagent configs, or custom agent references
- package manager scripts and repo docs that reveal test/build/lint commands

## Output shape

```markdown
## Capability summary

- Skills: ...
- Plugins: ...
- MCP servers: ...
- Hooks: ...
- Subagents/custom agents: ...
- Project commands: ...
- Missing or unavailable: ...
```
