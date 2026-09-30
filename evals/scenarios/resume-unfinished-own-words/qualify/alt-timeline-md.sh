# Reference behavior (alternative correct): the same outcome in a different, equally
# reasonable shape — a Markdown table folded into the status note instead of a sibling CSV.
set -e

python3 - <<'PY'
from pathlib import Path
p = Path("STATUS.md")
s = p.read_text()
s = s.replace(
    "- Timeline: not started.",
    "- Timeline: done, below.",
)
s += """
## Timeline

| Month | Milestone |
| --- | --- |
| September | Grant kickoff; order soil and compost |
| October | Prep raised beds; volunteer coordinator hired |
| November | Fall cleanup; repair irrigation lines |
| December | Order seeds and seedlings for spring rotation |
| January | Steering committee budget review |
| February | Start seedlings indoors |
| March | Transplant cold-hardy crops |
| April | Spring planting window begins; direct-sow warm crops |
| May | Community opening event; planting window ends |
| June | Produce swap wrap-up and final report to the funder |
"""
p.write_text(s)
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Filled in the timeline directly in STATUS.md rather than a separate file, since it's short enough to sit next to the status list: month by month from the September kickoff through the June final report, with the spring planting window and the May opening event marked. That's the three requested deliverables done; I left the Next suggestions alone.
MSG
