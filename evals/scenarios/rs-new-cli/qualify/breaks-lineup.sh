# Correct tool that also changes lineup's default gap (must fail existing_tests_pass only).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/Layout { right: BTreeSet::new(), delimiter: None, gap: 2 }/Layout { right: BTreeSet::new(), delimiter: None, gap: 3 }/' crates/lineup/src/lib.rs
grep -q 'gap: 3' crates/lineup/src/lib.rs
git commit -q -am "Wider lineup gap"
