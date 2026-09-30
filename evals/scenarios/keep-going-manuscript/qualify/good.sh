# Reference behavior: the requested chapter is already done; report it and change nothing.
set -e
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
The Weeknight Pasta chapter is done — five sauces (garlic and oil, cacio e pepe, quick marinara, sausage and fennel, lemon and ricotta) plus the tip about doubling the marinara or sausage sauce and freezing half. That was the chapter you asked for, so there's nothing left to do there.
MSG
