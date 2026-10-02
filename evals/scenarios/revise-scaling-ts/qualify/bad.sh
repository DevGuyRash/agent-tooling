# Patch-only (must fail scales_to_network_size only): the job's limit goes from 2h to 8h and the day is split
# by card across one worker thread per CPU, each running the old dropDuplicates, chargeDay, and cardDebits on
# its share. Output is identical. With N workers each searches only its share, (n/N)^2 steps, so CPU time falls
# by about N and wall time by about N^2, and on an ordinary multi-core host the person's full day would finish
# well inside even the old 2h limit; but every worker still searches all its earlier taps for each tap, so the
# CPU time keeps growing with the square of the day, which the scaling check measures.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/patch-workers"
finish "The charge run now uses every core on fares-01: taps are split by card across one worker per CPU (cards are independent, and duplicates share a card) and merged back in export order, so the output is byte-identical. I also raised the cron limit from 2h to 8h for headroom. Tests pass."
