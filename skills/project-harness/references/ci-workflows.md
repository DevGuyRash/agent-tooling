# CI and Cross-OS Workflows

Load this file for GitHub Actions decisions.

## Templates in this skill

Generated templates:
- `<skills-file-root>/assets/workflow-ci-just.yml.tpl`
- `<skills-file-root>/assets/workflow-ci-direct.yml.tpl`
- `<skills-file-root>/assets/workflow-release-cross-os.yml.tpl`

Example-only template:
- `<skills-file-root>/assets/workflow-release-assets-cross-os.yml.tpl`

## Quality rules for generated workflows

Generated workflows should:
- check out the repo explicitly
- set up the required language toolchains explicitly
- run bootstrap/install before lint/test/build
- use minimal permissions by default
- set a shell explicitly for run steps
- use concurrency for ordinary CI
- keep cross-OS packaging separate from ordinary PR checks

## CI mode guidance

### `just`

Use when:
- the repo is small or moderately sized
- a single Linux CI job is enough at first
- `just ci` should stay authoritative

Flow:
1. checkout
2. setup language tools
3. install `just`
4. run `just bootstrap`
5. run `just ci`

### `direct`

Use when:
- the repo is polyglot
- the repo is a workspace or monorepo
- CI steps need to stay visible
- matrices or artifacts are involved

Flow:
1. checkout
2. setup language tools
3. run bootstrap commands directly
4. run formatting, lint, and test steps directly

## Cross-OS workflow policy

The generated `release-cross-os.yml` is artifact-first.
It builds on Linux, Windows, and macOS, stages into `dist/<platform-id>/`, and
uploads those directories as artifacts.

That is the right default when:
- you need build verification across platforms
- you want distributable outputs
- you do not yet want to commit binaries

If you need true Release assets attached to a tag, start from the example
release-assets template instead of overloading ordinary CI.

## Toolchain version policy

Generated workflows use evergreen version selectors where available:
- Node: `lts/*`
- Go: `stable`
- Python: `3.x`
- Elixir/OTP: `> 0` (latest stable, excludes RCs)

Java and .NET require a major version number. The generated defaults target
the current LTS release with an inline comment reminding you to update when
a newer LTS ships. Java uses `check-latest: true` to get the freshest patch.

## Runner assumptions

These templates assume GitHub-hosted runners and current official action majors.
On current hosted runners:
- `ubuntu-latest` is x64
- `windows-latest` is x64
- `macos-latest` is arm64

That means the default macOS dist artifact is `macos-arm64`.
If the project needs macOS x64 too, fork the matrix intentionally.

## Public versus private repositories

Public open-source repos can often afford a richer artifact or release workflow.
Private repos should account for Actions minutes and artifact storage before
adding large matrices or long retention periods.

## Self-hosted and GHES caution

The shipped templates target current hosted-runner behavior. For older self-hosted
runners or GitHub Enterprise Server, you may need older action major versions.
Keep the harness logic, but downgrade action versions intentionally.
