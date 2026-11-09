# PZmap

A portable agent plugin for creating and maintaining custom setups in [PZmap](https://pzmap.org/) or a compatible deployed viewer. It supports arbitrary user-selected locations and purposes, rather than shipping a particular player's coordinates or a maintained loot database.

The bundled [`pzmap` skill](skills/pzmap/SKILL.md) covers coordinate and floor handling, native icon discovery, category styling, groups and notes, bulk imports, share links, preservation of existing markers, visibility troubleshooting, and reload/export verification. It directs the agent to discover the deployed viewer's capabilities instead of treating a historic menu, icon identifier, storage key, or share codec as a permanent contract.

## Use

Ask the agent to use `pzmap`, provide the destination map URL, and describe the setup. Coordinates can come from supplied records or separately verified map research. Examples:

- Create a collection of meeting places and resource locations with distinct native symbols.
- Restyle an existing collection without changing its coordinates or personal annotations.
- Combine several collections, retaining distinct floors and reconciling duplicate identities.
- Repair an import whose records exist but whose icons, floors, or search visibility are wrong.

Use `$pzmap` on a host that supports dollar-prefixed skill invocation. Other hosts expose the bundled skill through their own discovery and invocation surfaces.

## Runtime and distribution

The package supports Codex and Claude through native manifests and the same skill payload. It installs no browser extension, MCP server, hook, scheduled task, external service, or game mod. Agentic Design & Evaluation is authoring guidance, not a runtime dependency.

Reading public pages and supplied exports supports preparation. Verifying rendered icons, import acceptance, reload persistence, and browser-specific behavior requires an authorized interactive browser, or a user-mediated browser check. A code-capable local runtime is useful for conversion and assertions; the package does not prescribe a particular browser controller or compiler.

The user's request authorizes the requested setup, not unrelated storage changes. The skill keeps imports additive or explicitly scoped, preserves a recoverable baseline, and obtains separate approval for destructive replacement or public publication.

## Resources

- [Skill entry](skills/pzmap/SKILL.md): the operation's core contract and workflow.
- [Discovery and transfer](skills/pzmap/references/discovery-and-transfer.md): deployed capability discovery, native formats, codecs, and fallback adapters.
- [Appearance and visibility](skills/pzmap/references/appearance-and-visibility.md): native symbols, styling, floors, grouping, and missing-marker diagnosis.
- [Safe updates and verification](skills/pzmap/references/safe-updates-and-verification.md): merge identity, backups, rollback, acceptance, and delivery.
- [Behavior scenarios](tests/behavior-scenarios.md): scenarios for comparative agent trials, separate from structural checks.

## Package checks

From the repository root:

```sh
python3 -m unittest discover -s plugins/pzmap/tests -p 'test_*.py'
python3 scripts/plugin_port.py roundtrip plugins/pzmap --to codex --tmp .local/tmp/pzmap-codex
python3 scripts/plugin_port.py roundtrip plugins/pzmap --to claude --tmp .local/tmp/pzmap-claude
python3 scripts/plugin_port.py validate .local/tmp/pzmap-codex/pzmap-codex --host codex
python3 scripts/plugin_port.py validate .local/tmp/pzmap-claude/pzmap-claude --host claude
```

The package checks establish structure and conversion fidelity. They do not establish live PZmap compatibility, implicit skill selection, or improved agent behavior. Those require the corresponding browser evidence or comparative trials.

## Rights

The plugin's original instructions are MIT-licensed. PZmap software, game-derived data, map imagery, and third-party icon assets have their own rights and terms; this package grants no additional rights to them.
