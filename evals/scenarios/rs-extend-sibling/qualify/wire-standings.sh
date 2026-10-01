# Shared by the reference behaviors (not an arm): register a `standings` module in td's main.rs, dispatch the
# command to it, and list it in the usage text. The module itself is the caller's.
set -e
sed -i 's/^mod players;$/mod players;\nmod standings;/' crates/td/src/main.rs
sed -i 's/^        "card" => card::run(rest),$/&\n        "standings" => standings::run(rest),/' crates/td/src/main.rs
sed -i 's/^       td card FILE NO";$/       td card FILE NO\n       td standings [--after-round N] [--tiebreaks LIST] FILE";/' crates/td/src/main.rs
grep -q '^mod standings;$' crates/td/src/main.rs
grep -q '"standings" => standings::run(rest),' crates/td/src/main.rs
grep -q 'td standings \[--after-round N\]' crates/td/src/main.rs
