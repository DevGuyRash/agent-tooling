# Shared by the reference behaviors (not an arm): register `replay` (and, with an argument, more modules) in
# pagerlog's main.rs, dispatch the command, and list it in the usage text. The modules themselves are the
# caller's.
set -e
for m in replay "$@"; do
  sed -i "s/^mod receivers;\$/mod receivers;\nmod $m;/" crates/pagerlog/src/main.rs
  grep -q "^mod $m;\$" crates/pagerlog/src/main.rs
done
sed -i 's/^        "top" => top::run(rest),$/&\n        "replay" => replay::run(rest),/' crates/pagerlog/src/main.rs
sed -i 's/^       pagerlog top \[--limit N\] HISTORY";$/       pagerlog top [--limit N] HISTORY\n       pagerlog replay --routes FILE HISTORY";/' crates/pagerlog/src/main.rs
grep -q '"replay" => replay::run(rest),' crates/pagerlog/src/main.rs
grep -q 'pagerlog replay --routes FILE HISTORY";' crates/pagerlog/src/main.rs
