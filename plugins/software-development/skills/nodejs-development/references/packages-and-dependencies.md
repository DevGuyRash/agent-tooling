# Node.js Packages and Dependencies

Load this reference when the work touches `package.json`, exports/imports, workspaces, lockfiles, dependencies, install behavior, or published artifacts.

## Preserve Package-Manager Ownership

- Infer the manager and version from repository instructions, `packageManager`, lockfile, CI, and workspace configuration.
- Run repository scripts through that manager and preserve frozen or immutable install expectations.
- Do not hand-edit lockfile internals or create another manager's lockfile.
- Scope commands to the owning workspace when the repository supports it; check whether root and package manifests both change.

## Manifest Semantics

- Treat `name`, `version`, `type`, `main`, `module`, `types`, `exports`, `imports`, `bin`, `files`, `sideEffects`, `engines`, and publish configuration as compatibility-sensitive.
- Prefer an exports map only when the supported runtime and consumers can resolve it. Adding one encapsulates undeclared deep paths; once present, verify every previously supported and documented subpath, self-reference, and condition.
- Order conditional-export keys from specific to general and include a compatible default when unknown runtimes are supported; object key order participates in resolution.
- Keep runtime, development, peer, and optional dependencies in the category that matches who installs and provides them.
- Keep command shims portable and verify their shebang, permissions, entry file, and exit behavior when publishing a CLI.
- Inspect the packed artifact rather than assuming source-tree contents match publication.

## Dependency Changes

- Establish why a dependency is needed and whether the platform or an existing dependency already provides the behavior.
- Review direct and transitive version changes, lifecycle scripts, native addons, platform constraints, license, maintenance, security, and bundle or startup cost as relevant.
- Avoid unrelated upgrades and broad lockfile churn.
- Preserve the repository's semver-range policy. Do not widen or pin ranges without a release or reproducibility reason.
- Verify peer compatibility and supported Node versions before upgrading a library or types package.
- Treat automated audit output as evidence to triage, not an instruction to force upgrades that break the supported graph.

## Workspaces and Distribution

- Preserve workspace protocol and local-link conventions used by the manager.
- Check dependents when a workspace export, bin, declaration, or package name changes.
- Run the repository's pack, publish-dry-run, or distribution verification when available.
- Ensure secrets, local configuration, tests, source maps, and build inputs enter the package only when intended.
- Publish or change registry state when the work includes it, through the credentials the host provides, and run lifecycle scripts only from trusted packages.

Primary manifest authority: [Node.js packages documentation](https://nodejs.org/api/packages.html). Installation and lockfile semantics come from the repository-selected package manager.
