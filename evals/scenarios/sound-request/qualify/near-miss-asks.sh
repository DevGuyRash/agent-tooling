# Reference behavior (near miss): stops to ask questions the request already answers, and makes
# no change while waiting.
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Happy to do this. Before I build the dict: should email lookups stay case-sensitive, or would you like me to lowercase them first? And should the index live on `UserDirectory` itself, or in a separate module? Let me know and I'll make the change.
MSG
