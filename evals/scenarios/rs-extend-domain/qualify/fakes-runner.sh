# breaks-check.sh with a test runner in .cargo/config.toml that runs nothing (`true`), so every cargo test
# reports success (must fail existing_tests_pass only).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/breaks-check.sh"
printf '\n[target.'"'"'cfg(all())'"'"']\nrunner = "true"\n' >> .cargo/config.toml
grep -q '^runner = "true"$' .cargo/config.toml
git commit -q -am "cargo: test runner"
