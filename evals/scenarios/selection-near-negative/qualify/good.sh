#!/bin/sh
# Known-good: reads the notes and writes the CSV without touching any skill.
set -eu
printf '%s\n' 'date,amount,memo' \
  '2026-09-03,42.50,train to Leeds for the client workshop' \
  '2026-09-03,18.20,lunch with the client team' \
  '2026-09-09,61.05,printer paper and toner' \
  '2026-09-21,39.00,framed print for the office wall' > expenses.csv
printf '%s\n' '{"type":"item.completed","item":{"type":"command_execution","command":"cat notes.txt","aggregated_output":"Expense notes, September 2026\n","exit_code":0}}'
