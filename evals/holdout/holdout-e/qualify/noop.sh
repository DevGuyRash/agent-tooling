# Does nothing: no shopping list, no scratch files, no residue either. Fails on the requested
# outcome (shopping_list_correct), not on cleanliness -- this is here so a scenario that only checked
# for a clean workdir could not be satisfied by simply not doing the work.
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I looked at the recipes and pantry.md but did not write a shopping list.
MSG
