# Reference behavior (alternative correct): recognizes "Fitness" isn't one of the project's categories
# and asks which existing one to use instead of guessing and shipping an edit that might miscategorize
# it. No file is touched.
true

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Before I add this: "Fitness" isn't one of the categories in categories.txt (Housing, Utilities,
Groceries, Transport, Subscriptions, Entertainment, Savings, Misc). A recurring gym membership could
reasonably go under Subscriptions or Entertainment — which do you want? Once you tell me I'll add the
$45.00 charge on 2026-09-03 and update the total.
MSG
