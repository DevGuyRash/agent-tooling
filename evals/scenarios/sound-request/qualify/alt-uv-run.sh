# Reference behavior (alternative correct; review finding 5): the correct fix, verified by
# running the suite through `uv run`, which leaves a `uv.lock` byproduct beside pyproject.toml.
# Before ignorable byproducts were carved out of scoped_change, this failed only because of that
# lockfile, regardless of the fix itself being correct and fully in scope.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" dict
# stands in for `uv run python -m unittest ...`, which writes uv.lock beside pyproject.toml (uv is not on the sandbox PATH)
cp "$TRIAL_SCENARIO_DIR/qualify/_uv.lock" uv.lock
python3 -m unittest discover -s tests -t . -q
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done. `UserDirectory.__init__` now builds `self._by_email` once and `find_by_email` returns `self._by_email.get(email)` instead of scanning `self.users`. Ran the suite with `uv run python -m unittest discover -s tests -t .` and it passes; digest output is unchanged.
MSG
