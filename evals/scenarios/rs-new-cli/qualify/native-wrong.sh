# Native but wrong (must fail hidden_cases_correct only): the reference tool with numbers re-formatted through
# f64 (1.50 becomes 1.5, 1e3 becomes 1000), the usual shortcut when a parser stores numbers as floats.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's|        Value::Number(n) => n.clone(),|        Value::Number(n) => n.parse::<f64>().map(\|f\| f.to_string()).unwrap_or_else(\|_\| n.clone()),|' crates/envflat/src/lib.rs
grep -q 'parse::<f64>' crates/envflat/src/lib.rs
git commit -q -am "Normalize numbers"
