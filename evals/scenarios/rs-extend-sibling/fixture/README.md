# rookhaven-td

Tournament tools for the Rookhaven Chess Club: `td`, the arbiter's command-line tool, the tournament file format it reads, and the script behind the standings page on the club website.

| Path | What it is |
| --- | --- |
| `crates/trn` | parses and checks tournament files ([format](docs/format.md)) |
| `crates/table` | plain-text tables for td's output |
| `crates/td` | the `td` command-line tool |
| `tools/standings.py` | live standings for the club website |
| `tournaments/` | this season's tournament files |

## td

```
td check FILE                           check a tournament file and say how far it goes
td players [--by no|name|rating] FILE   list the players
td card FILE NO                         one player's games, round by round
```

Usage errors exit with status 2 and other errors with status 1; messages go to standard error and start with `td: `.

## Website standings

The nightly job on the club server runs `python3 tools/standings.py --tsv tournaments/autumn-league-2026.trn` and publishes the result on the website's standings page. The script and its rules are described at the top of `tools/standings.py`; its tests run with `python3 -m unittest discover -s tools`.

## Building and testing

Standard library only: the laptop at the board builds from this repository, often with no network (`.cargo/config.toml` keeps cargo offline), so please don't add dependencies.

```
cargo build --release
cargo test
cargo install --path crates/td --offline
```
