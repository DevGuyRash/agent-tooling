# Reference behavior: no heal at all - only grep/jq/python3 over $HOME, to show the native logs this
# scenario plants are findable by the same plain tools an agent already reaches for, not by a
# purpose-built parser. This is not an attempt at the healing task: it makes no repository change,
# so it is expected to fail every `required` check except native_logs_unchanged (it touches nothing
# under $HOME either). See qualify/README.md.
set -e

echo "== native log files under \$HOME ==" >&2
find "$HOME/.codex/sessions" "$HOME/.claude/projects" -name '*.jsonl' | sort >&2

echo "== per-host session count (grep, no parser) ==" >&2
codex_n=$(find "$HOME/.codex/sessions" -name '*.jsonl' | wc -l)
claude_n=$(find "$HOME/.claude/projects" -name '*.jsonl' | wc -l)
echo "codex: $codex_n  claude: $claude_n" >&2
[ "$codex_n" -eq 4 ]
[ "$claude_n" -eq 3 ]

echo "== every user turn, oldest first (jq, one line per session) ==" >&2
for f in $(find "$HOME/.codex/sessions" -name '*.jsonl' | sort); do
  jq -r 'select(.type=="event_msg" and .payload.type=="item_completed" and .payload.item.type=="UserMessage")
         | .payload.item.content | map(.text) | join(" ")' "$f"
done
for f in $(find "$HOME/.claude/projects" -name '*.jsonl' | sort); do
  jq -r 'select(.type=="user" and (.message.content|type)=="string") | .message.content' "$f"
done > /tmp/qualify-claude-user-turns.$$
cat /tmp/qualify-claude-user-turns.$$ >&2

echo "== the developer's complaint, found by grep alone across every native log ==" >&2
grep -rl "golden update took longer" "$HOME/.codex/sessions" "$HOME/.claude/projects"

echo "== each slip's own command and output, found by grep alone ==" >&2
grep -rl "69 insertions(+), 69 deletions" "$HOME/.claude/projects"                  # missing --indent (schwab-dividends)
grep -rl "FAILED (failures=1)" "$HOME/.codex/sessions"                              # only the expected file regenerated (chase-refunds)
grep -rl "missing column 'Posting Date' for bank 'chase'" "$HOME/.claude/projects"  # wrong --bank (schwab-parens)
grep -rl "6 insertions(+), 150 deletions" "$HOME/.codex/sessions"                   # skipped pretty-print (strip-card-numbers)

echo "== python3, for the one fact grep/jq can't express: which sessions ran the manual regen loop ==" >&2
python3 - "$HOME/.codex/sessions" "$HOME/.claude/projects" <<'PY'
import json, sys
from pathlib import Path

manual, hosts = 0, {"codex": 0, "claude": 0}
for root, host in ((sys.argv[1], "codex"), (sys.argv[2], "claude")):
    for f in Path(root).rglob("*.jsonl"):
        hosts[host] += 1
        text = f.read_text(errors="replace")
        if "json.tool" in text and "--sort-keys" in text:
            manual += 1
print(f"sessions with the manual json.tool --sort-keys regen step: {manual}", file=sys.stderr)
assert manual == 5, manual
assert hosts == {"codex": 4, "claude": 3}, hosts
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Not a heal: this reference only shows the native logs are findable with grep, jq, and python3 over
$HOME, with no built-in knowledge of this scenario. It located all 7 sessions (4 Codex rollouts
under ~/.codex/sessions/, 3 Claude Code transcripts under ~/.claude/projects/), read the developer's
"golden update took longer than the change itself. Again." complaint verbatim with grep, and picked
out the specific command/output evidence for all four regeneration slips (missing --indent, only the
expected file regenerated, wrong --bank, skipped pretty-print) the same way. No repository file was
read or changed.
MSG
