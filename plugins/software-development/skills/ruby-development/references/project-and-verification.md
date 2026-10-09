# Project Contract and Verification

Read this reference for Ruby version, Bundler, gem, dependency, native-extension, project-metadata, or verification work.

## Discover the project shape

Inspect applicable configuration rather than assuming a conventional Rails or gem layout:

- `.ruby-version`, `.tool-versions`, mise files, Gemfile, `Gemfile.lock`, gemspecs, and `.bundle/config`.
- `required_ruby_version`, dependency groups, platforms, sources, git/path dependencies, and native gems.
- CI matrices, containers, deployment buildpacks, server runtime, and operating-system support.
- Rake tasks, binstubs, executables, test helpers, autoloaders, and generated code.
- RSpec, Minitest, Cucumber, RuboCop, Standard, RBS, Steep, Sorbet, SimpleCov, or other configured tools.

In a monorepo, locate the Gemfile and gemspec that own the changed code. Root and nested Bundler contexts may differ.

## Preserve the runtime contract

Reconcile declared Ruby constraints with CI, deployment, framework support, and downstream gem consumers. Do not select features based only on the local `ruby --version`.

Account for engine and platform where relevant: MRI, JRuby, TruffleRuby, Windows, and native extensions can differ. If project declarations conflict, follow the one CI and the runner exercise and name the conflict.

## Manage dependencies intentionally

- Use the repository's Bundler version and invocation, commonly `bundle exec` for project tools.
- Prefer `bundle check` or the established locked install path before resolving dependencies.
- Run `bundle update` only when updating resolution is part of the task; scope updates when possible.
- Verify the resulting lock graph, sources, platforms, checksums when present, and the Bundler version that consumers use; a successful local require does not prove the locked artifact or loaded gem came from the intended source.
- Preserve groups, platforms, sources, credentials boundaries, and gemspec-versus-Gemfile ownership.
- Follow repository policy for `Gemfile.lock`; application and reusable-gem needs differ, so neither always-commit nor always-ignore is universal.
- Do not hand-edit generated lock state or broad-update unrelated gems.

## Build verification evidence

Use project interfaces first. A proportionate sequence is:

1. Syntax/load or focused example for the changed behavior.
2. Targeted test through the configured runner.
3. Configured style and type/signature checks.
4. Relevant integration suite for autoloading, callbacks, persistence, or framework lifecycle.
5. Supported Ruby/engine/platform matrix for compatibility-sensitive work.
6. Gem build and content inspection for packaging changes.

Do not introduce RSpec, Minitest, RuboCop, Standard, RBS, or Sorbet solely to verify one change. Report the exact command, scope, runtime, result, and any unavailable evidence.
