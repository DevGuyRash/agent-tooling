# ADR 0025: Centralize comparative method in a declarative skill

- Status: Accepted
- Date: 2026-08-31

## Decision

Split Testing is the repository's single owner of generic comparative-evidence method. Its runtime is a compact declarative skill with four conditionally loaded references. It owns neither domain truth, maker values, audit disposition, a universal evidence format, nor an execution harness.

Skill Auditor delegates every newly needed comparison to `$split-testing` in ordinary context while retaining claim selection, authority interpretation, materiality, severity, repair, release, reopening, and disposition. The plugins remain independently installable and declare no hard dependency. If Split Testing is unavailable, Skill Auditor may assess existing evidence but does not recreate comparative method; insufficient evidence leaves the claim and its audit consequence unresolved in plain-language material state.

Native evidence remains authoritative in whatever representation fits the work. Host-native sessions, workspaces, processes, files, conversations, people, or systems may be used when the live decision warrants them. No caller schema, custody lifecycle, bundled executable, directory convention, worker report, reviewer panel, visualization package, or persistent artifact is required by the plugin.

## Evidence

The architecture was selected through frozen outcome trials rather than by retaining every plausible mechanism. A declarative core, that core plus binding workspace and continuity rules, and that architecture plus a verified-opacity utility were compared with immutable Split Testing 1.0.1 and the earlier 2.0 implementations.

Broad cross-domain screens established parity but did not distinguish architectures. A targeted collision and failure-attribution trial showed that the declarative core independently chose separate native roots, preserved outputs, validated the decisive checker premise, and attributed a defective brief correctly. The binding-hygiene candidates reached the same decision with additional launch failures, retries, and artifacts.

A prospective identity, path, and order nuisance trial gave all three candidates the same correct, bounded judgment. The declarative core created a neutral native presentation without a bundled helper. The opacity utility worked mechanically but did not prevent an error and introduced an extra bundle plus a failed isolated launch. Under the frozen selection rules, the binding rules and utility therefore did not earn permanent runtime cost. External model critique agreed with this interpretation but was not acceptance authority.

## Consequences

Split Testing 2.0 ships only `SKILL.md`, four direct references, metadata, tests, and its license. The earlier Rust crate, packaged binaries, caller schemas, custody workflow, evidence reader, view server, release hooks, and role-specific file conventions are removed. Visualization remains an optional semantic presentation responsibility after evidence exists, never evidence authority.

Skill instructions preserve fresh context, native evidence, prospective decisions, legitimate authority, decisive-premise verification, task-versus-agent-versus-instrument attribution, and causal restraint without turning those relationships into stages, roles, fixed counts, schemas, or files. Simple comparisons may remain conversational; complex comparisons may use as much task-native structure as their actual hazards require.

Reopen this decision only if fresh outcome evidence shows a recurring material failure that the declarative skill does not cause agents to address and a narrower mechanism prospectively prevents without comparable regression, context cost, or ceremony. Mechanical correctness or tidier records alone is insufficient.
