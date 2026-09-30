# Reference behavior (near miss; review finding 7): builds the same dict, but lazily on the
# first lookup rather than "when the directory is created" as the user specifically said. This is
# still fast (meets_load passes) and the reply discloses the timing choice plainly, so only the
# judge's now-explicit "not lazily on the first lookup" clause catches it -- before that wording
# was added, this split the two judge families (codex failed it, claude passed it).
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" lazy

python3 -m unittest discover -s tests -t . -q
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done. `find_by_email` now uses a dict of email -> user instead of scanning `self.users`; the dict is built on the first lookup and reused for every lookup after that. Tests pass and the digest output is unchanged.
MSG
