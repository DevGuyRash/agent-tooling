# Reference: the planted logs read back with the self-healing skill's own current-format reader
# (gather.py) instead of finds-native-logs.sh's fixed phrase list - the check a "gatherer" arm of the
# three-arm experiment this scenario serves would actually run. gather.py is still unmerged, in-progress
# work (plugins/agentic-design-and-evaluation/skills/self-healing/scripts/gather.py on
# feat/self-healing-gather - see qualify/README.md), so this script soft-skips (exit 0, with a clear stderr
# note) rather than fail a run that has no way to reach it; set TRIAL_GATHER_PY to its path, and add its
# directory to this arm's own "readable" (see references/trials.md), to actually exercise it.
#
# Makes no repository change beyond good.sh's own (needed so the checkout resolves as a real git repo for
# gather.py's workspace.md); its own exit code is the signal, the same as finds-native-logs.sh.
set -e
GATHER="${TRIAL_GATHER_PY:-}"
if [ -z "$GATHER" ] || [ ! -f "$GATHER" ]; then
  echo "skip: TRIAL_GATHER_PY not set to the self-healing skill's gather.py (unmerged work; see qualify/README.md)" >&2
  exit 0
fi
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh" >/dev/null
OUT="$PWD/../gather-out"
python3 "$GATHER" --out "$OUT" --force
python3 - "$OUT/index.md" <<'PY'
import sys

text = open(sys.argv[1]).read()
rows = [l for l in text.splitlines() if l.startswith("| codex") or l.startswith("| claude")]
assert len(rows) == 7, f"expected 7 session rows in index.md, found {len(rows)}:\n{rows}"
empty = []
for row in rows:
    cells = [c.strip() for c in row.strip("|").split("|")]
    # | host | session | agent | start | end | cwd | user msgs | agent msgs | tool calls | ...
    user_msgs, agent_msgs, tool_calls = int(cells[6]), int(cells[7]), int(cells[8])
    if user_msgs + agent_msgs + tool_calls == 0:
        empty.append(row)
assert not empty, f"gather.py recovered no user/agent/tool entries from: {empty}"
print(f"gather.py recovered conversation content from all {len(rows)} planted sessions")
PY
