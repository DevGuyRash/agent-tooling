#!/bin/sh
# Nightly at 02:30, after the storefront has written its export: check it, then upload it to the newsletter
# service. Run by the ops box's cron as: nightly-sync.sh /srv/exports/customers-$(date +%F).csv
set -eu
export_file="$1"
cd "$(dirname "$0")/.."
python3 -m shopcrm validate "$export_file"
python3 -m shopcrm stats "$export_file"
newsletter upload --list customers --replace "$export_file"
