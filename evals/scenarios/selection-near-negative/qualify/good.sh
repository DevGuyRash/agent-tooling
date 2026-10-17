#!/bin/sh
# Known-good: reads the notes and writes the CSV without touching any skill.
set -eu
printf '%s\n' 'date,amount,memo' \
  '2026-09-03,42.50,train to Leeds for the client workshop' \
  '2026-09-03,18.20,lunch with the client team' \
  '2026-09-09,61.05,printer paper and toner' \
  '2026-09-21,39.00,framed print for the office wall' > expenses.csv
printf '%s\n' '{"finished": true, "covers": ["message", "command", "edit", "read", "load", "other"], "actions": [{"turn": 1, "kind": "command", "command": "cat notes.txt", "exit_code": 0, "output": "Expense notes, September 2026\\n"}]}' > "$TRIAL_RECORD"
