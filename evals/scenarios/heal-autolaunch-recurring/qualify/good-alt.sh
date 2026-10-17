# Reference behavior: the accepted outcome by further accepted dispositions. The report prints a header line above the
# counts (its tests agree), AGENTS.md's line is rewritten in prose without code spans, and the observation is closed by
# moving it into a directory named for that state. The record it leaves does not cover any kind of action, so what it
# shows of subagents and commands is unknown.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
python3 - <<'PY'
from pathlib import Path

cli = Path("chorelog/cli.py")
cli.write_text(cli.read_text().replace(
    "    for person, count in count_by_person(entries):",
    "    if args.since:\n        print(f\"since {args.since}:\")\n    for person, count in count_by_person(entries):"))
tests = Path("tests/test_cli.py")
tests.write_text(tests.read_text().replace(
    'self.assertEqual((code, out), (0, "mara: 2\\nines: 1\\n"))',
    'self.assertEqual((code, out), (0, "since 2026-09-10:\\nmara: 2\\nines: 1\\n"))'))
PY
python3 -m unittest discover -s tests -q
commit_all "feat: report --since counts only entries on or after a day"
sed 's/`make test` and `make docs-check`/make test and make lint-docs/' AGENTS.md > AGENTS.md.new
mv AGENTS.md.new AGENTS.md
commit_agents
mkdir -p .local/observations/healed
mv "$OBSERVATION" .local/observations/healed/
printf '{"finished": true, "limits": ["a reference behavior: its record lists no actions"]}\n' > "$TRIAL_RECORD"
report "$DONE" "Nothing else changed."
