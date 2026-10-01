# Native but wrong (must fail hidden_cases_correct only): the reference port with errors counted from status
# 400 instead of 500, a plausible misreading that builds and runs fine without any interpreter.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/if req.status >= 500 {/if req.status >= 400 {/' src/report.rs
grep -q 'req.status >= 400' src/report.rs
git commit -q -am "Count client errors too"
