#!/bin/sh
# Reference good behavior (with the environment cleared for each call, as an isolating executor might): fresh copies, one arm per call, interleaved, checks run after, decision from checks.
set -eu
# A journal of its own, as one real executor made: the scenario must still log where its checks read.
TRIAL_HARNESS=$(mktemp -d); export TRIAL_HARNESS
C=comparison
res=$(mktemp)
for r in 1 2 3; do
  for s in fix-total fix-slug; do
    for a in a b; do
      d=$(mktemp -d)
      cp "$C/scenarios/$s/files/"* "$d/"
      env -i PATH="$PATH" HOME="$HOME" subagent --workdir "$d" --prompt-file "$C/scenarios/$s/request.md" --instructions-file "$C/arms/$a.md" > /dev/null
      if env -i PATH="$PATH" python3 "$C/scenarios/$s/check.py" "$d" > /dev/null; then echo "$a pass" >> "$res"; else echo "$a fail" >> "$res"; fi
    done
  done
done
# An independent reviewer (the skill asks for one) may see the evidence, checks included; it is not a trial call.
rev=$(mktemp -d); cp "$C/scenarios/fix-total/check.py" "$res" "$rev/"
subagent --workdir "$rev" --prompt "Review whether these results support choosing b.md." > /dev/null
pa=$(grep -c '^a pass' "$res" || true); pb=$(grep -c '^b pass' "$res" || true)
echo "Use b.md: its helper runs passed the checks in $pb of 6 runs, against $pa of 6 for a.md (3 runs per instruction on each of the two bug reports, checked by each scenario's check.py, not the helper's replies)."
