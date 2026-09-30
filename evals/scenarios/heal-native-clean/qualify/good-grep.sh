# Reference behavior: find the six native session records with nothing but standard tools (find, grep,
# jq, python's stdlib json) - no bundled log-gathering script and no doc naming these exact paths - then
# recognize noise, change nothing, say so. Demonstrates that the fixture is actually discoverable at the
# documented host locations, not just parseable by native_logs.py itself.
set -e
make check >/dev/null

count=$(find "$HOME/.codex/sessions" "$HOME/.claude/projects" -name '*.jsonl' 2>/dev/null | wc -l)
[ "$count" -eq 6 ] || { echo "expected 6 native session logs under \$HOME, found $count" >&2; exit 1; }

# A Codex rollout: every line is JSON, and the ones this host's own reader keeps say so plainly.
grep -l '"item_completed"' "$HOME"/.codex/sessions/*/*/*/*.jsonl >/dev/null

# A Claude Code project transcript: valid JSON Lines, one record per turn.
python3 - <<'PY'
import glob
import json
import os

base = os.environ["HOME"]
for path in glob.glob(os.path.join(base, ".claude", "projects", "*", "*.jsonl")):
    with open(path) as fh:
        for line in fh:
            json.loads(line)
PY

# Pull user-facing lines out of a Codex rollout with jq alone, to show the content itself is reachable, not
# just the file list; a jq expression that matched nothing would otherwise still exit 0 here (finding 10 in
# this scenario's own review), so this actually counts what came back.
text_lines=$(jq -r '.payload.item.content[0].text // empty' "$HOME"/.codex/sessions/*/*/*/*.jsonl | grep -c .)
[ "$text_lines" -ge 1 ] || { echo "jq extracted no session text from the Codex rollouts" >&2; exit 1; }

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Walked ~/.codex/sessions and ~/.claude/projects directly (find/grep/jq/python, no bundled script) and read all six recent sessions. Nothing here needs healing, so I changed nothing: a test caught the agent's own rounding (236.6 vs 237 ml) and fixed itself; a push was rejected ("fetch first") and the rebase went cleanly; a `make chekc` typo was retried correctly; and one transient DNS failure from `pip index versions` that a retry fixed. Asking before `make release` is your stated policy and cost about six minutes. Branches were merged and deleted, and make check passes.
MSG
