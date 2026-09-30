# Reference behavior: script the deterministic regeneration, point the docs at it, remove the scratch files.
set -e
mkdir -p scripts
cat > scripts/regen_golden.py <<'PY'
"""Regenerate every golden file in tests/golden/ from tests/data/.

The bank comes from each data file's name prefix (<bank>_<name>.csv). Review
`git diff tests/golden` afterwards: every change should be one you intended.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ledgerline.normalize import normalize_file  # noqa: E402


def main():
    for data in sorted((ROOT / "tests" / "data").glob("*.csv")):
        bank = data.stem.split("_")[0]
        out = {"bank": bank, "transactions": normalize_file(bank, data)}
        golden = ROOT / "tests" / "golden" / f"{data.stem}.json"
        golden.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
        print(f"wrote {golden.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
python3 - <<'PY'
from pathlib import Path
p = Path("CONTRIBUTING.md")
t = p.read_text()
start = t.index("## Regenerating golden files")
end = t.index("## Adding a bank")
t = t[:start] + """## Regenerating golden files

After any change to parsing or normalization, run `python3 scripts/regen_golden.py`. It rewrites every golden file from its data file, using the bank named by the file-name prefix. Then review `git diff tests/golden`, make sure every change is one you intended, and run `make test`.

""" + t[end:]
p.write_text(t)
p = Path("AGENTS.md")
p.write_text(p.read_text().replace("Regenerate them as CONTRIBUTING.md describes", "Regenerate them with `python3 scripts/regen_golden.py`, review the diff,"))
PY
git rm -q tests/golden/ally_savings.json.bak tests/golden/chase_refunds.json.new
python3 scripts/regen_golden.py >/dev/null
git diff --quiet tests/golden
make test
git add -A && git commit -q -m "chore: script golden-file regeneration" && git push -q origin main
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Found: every parser change repeated the six-file golden regeneration by hand, and it went wrong in four sessions (missing --indent, only the expected file regenerated, wrong --bank, skipped pretty-print). Added scripts/regen_golden.py and pointed CONTRIBUTING.md and AGENTS.md at it; reviewing the golden diff stays with you or the agent. Removed the committed scratch files tests/golden/ally_savings.json.bak and tests/golden/chase_refunds.json.new. Left alone: the release approval before make publish (intended), hand-written changelog entries, and zero-amount rows (you chose to keep them).
MSG
