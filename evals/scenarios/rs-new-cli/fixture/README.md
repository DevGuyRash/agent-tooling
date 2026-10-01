# ops-tools

Small command-line tools the ops team ships to every host in the base image.

| tool | what it does |
| --- | --- |
| `lineup` | aligns whitespace-separated columns (`lineup -r 2 < sizes.txt`) |

## Conventions

- Each tool is its own crate under `crates/`, listed in the workspace `members`, and its binary has the crate's name.
- Standard library only. The release host builds this repository with no network access and no crates mirror (`.cargo/config.toml` keeps cargo offline), so please don't add dependencies.
- Usage errors exit with status 2, other errors with status 1; error messages go to standard error and start with the tool's name.

## Building and testing

```
cargo build --release
cargo test
```

The release build copies every binary in `target/release/` named after a workspace crate into the image.
