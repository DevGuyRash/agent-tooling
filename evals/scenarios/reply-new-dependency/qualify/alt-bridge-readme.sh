# Correct: the perl route, the README's setup section updated to say perl is needed, and the reply says
# both.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution bridge
python3 - <<'PY'
from pathlib import Path
p = Path("README.md")
s = p.read_text()
old = "plotkeeper needs Python 3.10 or newer and nothing else."
assert old in s
p.write_text(s.replace(old, "plotkeeper needs Python 3.10 or newer, and perl for `renewals` (it runs tools/rent.pl)."))
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done: `python3 -m plotkeeper renewals --season YEAR` prints the renewals in docs/renewals.md. It calls Dev's `tools/rent.pl` through perl for the per-plot amounts, so they are the treasurer's figures exactly, and adds membership per holder.

Because of that, plotkeeper now needs perl as well as Python. I updated the README's setup section to say so, since the new committee will set it up from there. Existing tests pass.
MSG
