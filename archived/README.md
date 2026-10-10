# Archived packages

These packages are retained for future resumption, outside active `plugins/` and
`skills/` discovery and both host marketplace catalogs:

- `skills/diagram`: the standalone Diagram skill, including its scripts,
  references and evaluation fixtures.
- `plugins/docker-architect`: the complete Docker Architect plugin for both hosts,
  including its launchers and delivered binaries.
- `plugins/goalspec`: the complete GoalSpec plugin, including Authoring Goals and
  its tests.

Visualization and its Mermaid skill remain active. Diagram is a separate package.
The Docker Architect Rust crates remain buildable in the workspace and read their
preserved reference data here. They do not register or install a skill.
`packaging/docker-architect-artifacts.toml` and `packaging/receipts/` preserve the
original delivery definitions and receipts as historical evidence, not current
verification receipts. They are excluded from the active artifact manifest.

## Existing installations

Removing catalog entries does not uninstall cached plugins. The repository's
`install-all` helper adds or refreshes selected active entries; it does not prune
workstation state. First remove these identities from the workstation owner's
maintained desired-state selection so the next reconciliation cannot reinstall
them. Inspect installed host names, scopes and project paths before removal.
For the matching user-scope identities, the native commands are:

```sh
codex plugin remove docker-architect@agent-tooling
codex plugin remove goalspec@agent-tooling
claude plugin uninstall --scope user --keep-data docker-architect@agent-tooling
claude plugin uninstall --scope user --keep-data goalspec@agent-tooling
```

For Claude project/local installations, use the actual installed scope and native
project directory instead. Preserve unrelated registrations and settings before
and after removal. Do not edit another scope by assumption. `--keep-data` retains
Claude plugin data; the source payloads remain here regardless of host caches.

Diagram was a standalone skill, not a marketplace plugin. Remove its exact entry
from the owner-managed skill source selection, then move the identified installed
`diagram` directory or symlink into a backup directory outside every host's skill
search roots. Do not remove Mermaid, Visualization, or an unrelated similarly
named package. Preserve manual changes and record the original location.

Restart the hosts or open fresh sessions after retirement so discovery reloads.
Verify the retired entries no longer appear and unrelated active plugins still do.

## Resume later

Restore the selected directory to its former root (`skills/diagram`,
`plugins/docker-architect`, or `plugins/goalspec`). Restore that plugin's entries
in both marketplace manifests from Git history, validate both host variants,
then publish and use the normal canonical installation flow. Restore only the
workstation selections that are actually wanted.

For Docker Architect, also restore its task blocks to `packaging/artifacts.toml`
and update the Rust reference paths back to `plugins/docker-architect/`. Regenerate
and verify task receipts against the restored current sources before publication;
archived receipts describe the old source layout and are not proof of a new build.
Content, executable modes and history are preserved by the archival move.
