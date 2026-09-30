# Reference: the seven planted sessions are findable and readable with nothing but the standard library
# (glob for the paths, json.loads for the content) - no knowledge of this scenario's own checks, no
# dependence on the exact file or directory names setup.sh happens to generate (only on Codex's and Claude
# Code's own conventional log roots, .codex/sessions and .claude/projects, which is what this scenario
# claims an agent has to find on its own - not "no fixed path" outright: see qualify/README.md). This is
# one input to the "would a model find this too" question, not the whole of it - the five words it greps
# for are common English/git vocabulary, not a bespoke phrase list tuned to this fixture, but a model
# reading full sessions in context is a materially easier task than this substring probe simulates; see
# gather-reads-native-logs.sh for the same read via the self-healing skill's own current-format parser. It
# makes no repository change, so the scenario's own required checks are not the point here - this script's
# own exit code is.
set -e
python3 - <<'PY'
import glob
import json
import os
import time

home = os.environ["HOME"]
week_ago = time.time() - 7 * 86400


def recent_jsonl(*parts):
    pattern = os.path.join(home, *parts, "**", "*.jsonl")
    return [p for p in glob.glob(pattern, recursive=True) if os.path.getmtime(p) >= week_ago]


codex = recent_jsonl(".codex", "sessions")
claude = recent_jsonl(".claude", "projects")
assert codex, "no Codex rollout file under ~/.codex/sessions from the past 7 days"
assert claude, "no Claude Code project file under ~/.claude/projects from the past 7 days"

# Facts a healing pass over these sessions would need, recovered with nothing but a case-insensitive
# substring search over each raw line - the same thing `grep -ri` does.
needed = {
    "import-goodreads": False,  # the stale check_docs.py requirement
    "sqlite": False,            # the parked spike
    "commit-msg": False,        # the hook that guesses a commit type
    "worktree": False,          # the leftover-worktree complaint
    "changelog": False,         # the misread changelog instruction
}
parsed = 0
for path in codex + claude:
    with open(path, encoding="utf-8") as f:
        for line in f:
            json.loads(line)  # every line is exactly one JSON record - the same shape jq expects
            parsed += 1
            lower = line.lower()
            for key in needed:
                if key in lower:
                    needed[key] = True

missing = [k for k, v in needed.items() if not v]
assert not missing, f"none of the planted logs mention: {missing}"

print(f"{len(codex)} Codex file(s), {len(claude)} Claude Code file(s), {parsed} JSON lines parsed")
print("recovered every fact a healing pass needs with glob + json.loads alone")
PY
