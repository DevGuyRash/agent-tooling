# Rust Commands

Use this file when the repo uses Rust.

## Detection priorities

- `Cargo.toml`
- workspace tables
- `[[bin]]` entries
- `src/main.rs`
- `examples/` only if examples are intentionally part of the command surface

## Default command family

```text
build      cargo build
release    cargo build --release
test       cargo test
lint       cargo clippy -- -D warnings
fmt        cargo fmt
fmt-check  cargo fmt --check
clean      cargo clean
bootstrap  cargo fetch
```

## Workspace variant

Prefer workspace-wide commands when the repo already acts like one project:

```text
cargo build --workspace
cargo test --workspace
cargo fmt --check
cargo clippy --workspace -- -D warnings
```

Add crate-specific recipes only when contributors need them.

## Dist patterns

Rust is one of the easiest ecosystems to support for staged binaries because
release outputs land in a predictable place.

### Single-platform dist

- build with `cargo build --release`
- stage from `target/release/<bin>`

### Cross-OS committed dist

- use `dist/<os>-<arch>/`
- stage the current platform’s release binary there
- commit all populated platform directories when clone-and-run is required

## Cross-compilation

There are three valid approaches:

1. native builds on each OS
2. CI matrix builds
3. explicit cross-compilation tooling such as target triples or platform-
   specific builder images

The harness does not force cross-compilation. Native per-OS builds are often
simpler and more reliable.

## Bootstrap realism

`cargo fetch` is a good minimal bootstrap.
`cargo build` is acceptable when the team wants a stronger readiness check.

## When not to guess

Do not auto-stage every crate in a large workspace. Only stage explicit binary
targets or packages that are clearly tools.
