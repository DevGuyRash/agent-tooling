#!/bin/sh
# The nightly fare run (cron on fares-01 at 04:30): charge the service day that just ended and hand the
# debits to billing before the 07:00 billing run.
set -eu
day=$(date -d yesterday +%F)
export_file="/srv/fares/exports/taps-$day.csv"
run_dir="/srv/fares/runs/$day"
timeout 8h node /opt/tapfare/bin/tapfare.ts charge "$export_file" --out "$run_dir"
cp "$run_dir/debits.csv" "/srv/billing/inbox/debits-$day.csv"
