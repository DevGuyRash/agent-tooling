# Alternative-correct (borderline, deliberately accepted — see qualify/README.md): a status
# summary that frames the outline as the plan, then asks before starting anything. It never says
# the outline chapters weren't requested, but it does not start writing any of them.
set -e
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Chapters 1 and 2 are written. Per the outline, next up is Chapter 3 (Sheet-Pan Dinners), then Soups for Stashing, Salads That Hold Overnight, and Desserts in Ten Minutes or Less. Want me to start on Chapter 3?
MSG
