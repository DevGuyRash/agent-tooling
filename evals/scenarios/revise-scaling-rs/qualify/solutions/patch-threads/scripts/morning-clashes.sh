#!/bin/sh
# The morning clash list (cron on desk-01 at 05:30): every clashing pair of upcoming bookings, printed at
# each centre's front desk before the doors open at 06:30.
set -eu
day=$(date +%F)
report="/srv/bookings/reports/clashes-$day.txt"
timeout 4h /opt/bookdesk/bin/bookdesk clashes /srv/bookings/export/upcoming.csv > "$report"
for desk in $(cat /srv/bookings/desks); do
  lp -d "$desk" "$report"
done
