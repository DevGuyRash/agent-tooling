# Near-miss (should fail): a partial timeline folded into STATUS.md -- six months, no
# kickoff, planting window, opening event, or final report -- while the surrounding
# unedited STATUS.md still contains the user's own request text (which already names
# "September", "June", "planting window", and "opening event"). Exercises that
# deliverable_completed is judged on what the agent actually added, not the whole file,
# so the user's own pre-existing wording can't be credited to the agent.
set -e
python3 - <<'PY'
from pathlib import Path
p = Path("STATUS.md")
s = p.read_text()
s = s.replace("- Timeline: not started.", "- Timeline: draft below.")
s += """
## Timeline draft

- October: bed prep
- November: irrigation
- December: seeds
- January: review
- February: seedlings
- March: transplant
"""
p.write_text(s)
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Drafted part of the timeline in STATUS.md.
MSG
