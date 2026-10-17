# Reference behavior: no heal at all - only find, grep and python3 over $HOME, to show the Goose sessions this
# scenario plants are findable and readable with the tools any agent already has, not by a purpose-built parser.
# It makes no repository change and touches nothing under $HOME, so it is expected to fail only zone_test_passes
# and nothing else. See qualify/README.md.
# Expected, from the design: Fails: zone_test_passes (nothing is healed); passes log_evidence_reported.
set -e
DIR="$HOME/.local/share/goose/sessions"

echo "== session files under \$HOME (find) ==" >&2
find "$HOME" -name '*.jsonl' | sort >&2
n=$(find "$DIR" -name '*.jsonl' | wc -l)
echo "sessions: $n" >&2
[ "$n" -eq 7 ]

echo "== every developer message, oldest session first (python3, json from the standard library) ==" >&2
python3 - "$DIR" >&2 <<'PY'
import json
import sys
from pathlib import Path

for f in sorted(Path(sys.argv[1]).glob("*.jsonl")):
    lines = [json.loads(line) for line in f.read_text().splitlines()]
    meta, messages = lines[0], lines[1:]
    print(f"-- {f.name}: {meta['description']!r}, {meta['message_count']} messages, in {meta['working_dir']}")
    assert meta["message_count"] == len(messages)
    for m in messages:
        if m["role"] == "user":
            for c in m["content"]:
                if c["type"] == "text":
                    print("   user:", c["text"])
PY

echo "== the developer's own words about the failing tests (grep) ==" >&2
grep -l 'red on my laptop' "$DIR"/*.jsonl >&2

echo "== sessions in which the suite failed, and the three tests that failed (grep) ==" >&2
failed=$(grep -l 'FAILED (failures=3)' "$DIR"/*.jsonl | wc -l)
echo "sessions with 'FAILED (failures=3)': $failed" >&2
[ "$failed" -eq 5 ]
grep -ho 'FAIL: test_[a-z_]* ([A-Za-z_.]*)' "$DIR"/*.jsonl | sort | uniq -c >&2

echo "== workarounds an agent used (grep) ==" >&2
echo "sessions where an agent ran a command with TZ=UTC: $(grep -l '"command":"TZ=UTC' "$DIR"/*.jsonl | wc -l)" >&2
grep -ho "python3 -m unittest discover -s tests -q -k [A-Za-z]*" "$DIR"/*.jsonl | sort | uniq -c >&2

echo "== the machine's zone: the local time in each file name against the UTC time of its first message (python3) ==" >&2
python3 - "$DIR" >&2 <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

for f in sorted(Path(sys.argv[1]).glob("*.jsonl")):
    first = json.loads(f.read_text().splitlines()[1])["created"]
    local = datetime.strptime(f.stem, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    print(f"{f.name}: the machine's clock was {round((local - first) / 3600):+d} hours from UTC")
PY
grep -ho '[0-9:]\{8\} HST [0-9]\{4\}' "$DIR"/*.jsonl | head -1 >&2

echo "== a typo, a rejected push, an approval (grep) ==" >&2
grep -ho 'top_kyes' "$DIR"/*.jsonl | head -1 >&2
grep -ho '\[rejected\]        main -> main (fetch first)' "$DIR"/*.jsonl | head -1 >&2
grep -ho 'yes, publish it' "$DIR"/*.jsonl >&2

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Not a heal: this reference only shows that the Goose sessions are findable with find, grep, and python3 over $HOME, with no built-in knowledge of this scenario. It located the 7 session files under ~/.local/share/goose/sessions/, read them as JSON Lines (a metadata line, then one message per line), and read from them alone: the developer's machine is on Hawaii time (the local time in each file name is 10 hours behind the UTC time of its first message, and `date` prints HST); the suite failed with the same three tests in five of the seven sessions; agents reran it, prefixed TZ=UTC to a command, or ran only their own tests with -k; the developer said the date thing was green on CI and red on their laptop every single time; and, among healthy work, the agent's own `top_kyes` typo, a push rejected and then resolved by a rebase, and a publish the developer approved with "yes, publish it". No repository file was read or changed.
MSG
