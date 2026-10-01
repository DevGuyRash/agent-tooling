# devtools

Small command-line tools the platform team uses for its reports. One crate, one binary per tool under `src/bin/`, shared helpers in `src/lib.rs`. No third-party crates: the report jobs build on machines without network access.

| Tool | What it prints |
| --- | --- |
| `todo-count` | TODO and FIXME markers in a source tree, by file |

```sh
cargo run --bin todo-count -- -n 10 ~/src/billing
cargo test
```

Reports share a format: a few `key: value` lines, then ranked lists printed with `devtools::count_line`.
