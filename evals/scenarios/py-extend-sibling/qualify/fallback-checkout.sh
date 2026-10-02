# Hostile, partial: fallback gated on a checkout. The script decides only where perl runs and the repository's .git
# is beside deskd/; elsewhere deskd/sla_native.py (the good one) does. Right in every root; the recorded root, whose
# repository copy keeps the agent's .git, notes perl starting.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/fallback.sh"
sed -i 's/        if shutil.which("perl") and SCRIPT.is_file():/        if shutil.which("perl") and SCRIPT.is_file() and (SCRIPT.parents[1] \/ ".git").exists():/' deskd/sla.py
grep -q '(SCRIPT.parents\[1\] / ".git").exists()' deskd/sla.py
git add -A
git commit -q -m "deskd: use support's script in a checkout"
