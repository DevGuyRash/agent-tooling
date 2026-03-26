# Detection Model

Load this file before choosing architecture or CI.

The harness should reflect what the repo already is, not what we wish it were.

## Detect these first

### Components

Identify each buildable or runnable component:
- root app
- service folders
- package workspaces
- crates
- Go commands
- Java modules
- .NET solutions/projects

### Languages and build tools

Detect at least:
- language set
- build tools
- package managers
- task runners
- frameworks when they materially affect commands

### Existing command surfaces

Check for:
- `Makefile`
- `Taskfile.yml` and variants
- package scripts
- existing GitHub workflows
- Dockerfiles and compose files

### Distribution hints

Check for:
- compiled binary targets
- existing `dist/`
- per-platform `dist/<os>-<arch>/` folders
- whether `dist/` is ignored
- whether `dist/` is tracked with Git LFS through `.gitattributes`

## Important default

Do **not** force a distribution strategy just because a compiled language exists.
A Rust or Go repo without `dist/` may still want:
- source-only development
- local-only dist
- committed dist
- artifact-only releases

Detection should inform the choice, not make it for you.

## Generated artifact directories

Detection skips directories that typically contain build outputs (`dist`, `build`,
`pkg`, `out`, `extension-dist`, `_build`, `.output`, `target`). Files like
`package.json` or `Cargo.toml` inside these directories are build artifacts,
not source components.

If a repo genuinely uses one of these names for source code, override by
adding the component manually in the state file.

## Environment variable leakage

Some tools (`trunk`, `deno`) interpret environment variables like `NO_COLOR`
as configuration. When the parent shell sets `NO_COLOR=1`, it leaks into
`just` recipes and may cause unexpected failures. This is not auto-fixed
because it is tool-specific. If encountered, unset the variable in the
affected recipe:

```just
my-recipe:
    unset NO_COLOR && trunk check
```

## No-example repos

If detection finds no convincing build surface:
- keep CI mode at `none`
- keep architecture at `general`
- generate placeholder recipes
- record notes in state

That is still a successful outcome.
