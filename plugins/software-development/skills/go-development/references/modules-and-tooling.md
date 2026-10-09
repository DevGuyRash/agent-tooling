# Go Modules and Tooling

## Resolve the effective build contract

- Identify the module root for every touched package. A repository may contain nested modules, a `go.work`, vendored dependencies, or generated subtrees.
- Resolve the `go` and `toolchain` directives using the behavior of every supported invoking toolchain. Record the effective language version, minimum-toolchain enforcement, and any per-file version constraints that affect touched packages.
- Respect repository `GOTOOLCHAIN`, workspace, proxy, checksum, private-module, and vendor policies without persisting new global configuration.
- Use the repository's wrapper, task runner, or CI command when it encodes flags, tags, environment, generation, or cross-platform behavior.

## Change dependencies narrowly

- Add or update only the module required by the task.
- Use Go commands to edit module metadata rather than hand-editing resolved indirect requirements.
- Run `go mod tidy` only when the task or repository workflow calls for it; inspect every `go.mod` and `go.sum` change it makes.
- Preserve intentional `replace`, `exclude`, `retract`, and local workspace directives. Do not publish a module with an accidental local replacement.
- If vendor mode is part of the repository contract, update and verify `vendor` consistently; otherwise do not introduce it.
- Review removed checksums, indirect changes, and module-path changes as behavior, not formatting noise.

## Respect packages, generation, and build selection

- Preserve build constraints, filename suffix selection, cgo conditions, and target-specific implementations.
- For every affected supported target, inspect both selected and complementary files so build constraints, filename suffixes, cgo/pure-Go alternatives, and version-constrained implementations select exactly one complete path. Widen only to the repository's declared matrix.
- Run an existing `go generate` directive only when its inputs or outputs are in scope. Inspect generated diffs and avoid editing generated output directly.
- Keep generation reproducible with repository-pinned tools where available; do not install latest generators globally.
- Check embed patterns and packaged files when moving or renaming resources.
- Treat cgo, plugins, race builds, and cross-compilation as platform contracts with their own availability limits.
- Preserve command entrypoints, exit codes, signals, environment variables, and standard streams when changing `main` packages.

## Avoid environment drift

- Do not modify `go env -w`, user module caches, global tool installs, or shell profiles unless the task requires durable environment changes.
- Do not assume network access. Distinguish missing cached dependencies from source failures.
- Do not bypass checksum or private-module policy to make a build pass.
- Never delete or regenerate module, workspace, vendor, or generated files merely because the local toolchain disagrees; first resolve the declared version and command.

## Review module-facing compatibility

- Preserve module and import paths unless migration is requested.
- For public modules, assess compatibility across supported Go versions and relevant operating-system/architecture targets.
- Verify that examples, commands, generated artifacts, and package docs still use the correct import path.
- Record intentional dependency, directive, workspace, vendor, or platform changes in the handoff.

Primary references: [`go.mod` reference](https://go.dev/doc/modules/gomod-ref), [toolchain selection](https://go.dev/doc/toolchain), [workspaces](https://go.dev/ref/mod#workspaces), [module commands](https://go.dev/ref/mod).
