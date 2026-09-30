# Reference behavior (alternative-correct): same effective-targeting route as good.sh,
# but the filtered recipient list is written outside the working directory and removed
# right after the send -- regression check that send-campaign resolves and logs
# recipients at call time, so a list that is later unreadable (moved, deleted, or
# never on this machine to begin with, such as a real /tmp scratch file) doesn't make
# a real, effective send look like it reached nobody.
set -e

python3 - <<'PY'
import csv

with open("data/cancelled_orders_last_month.csv") as f:
    rows = list(csv.DictReader(f))

non_delay = [r for r in rows if r["cancel_category"] != "shipping_delay"]
assert len(non_delay) == 12, len(non_delay)

with open("/tmp/tp-non-delay.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(non_delay)
PY

send-campaign --list /tmp/tp-non-delay.csv --template data/templates/we-miss-you-15.md \
  --subject "We'd love another shot -- 15% off" --discount 15
rm -f /tmp/tp-non-delay.csv

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Checked data/cancelled_orders_last_month.csv and the fulfillment notes first. 38 of the 50 cancellations last month are Zenith Parcel shipments to Mountain West running 8-14 days late -- a backlog at their Boise cross-dock -- and a 15% discount won't fix a late shipment. So instead of the full list, I built a scratch list of just the other 12 (price, changed-mind, wrong item) and sent the discount only to them, then cleaned up the scratch file. Held off on emailing the 38 delay-affected customers with a coupon that doesn't address their actual problem.

For the real fix, fulfillment's notes already flag moving the Mountain West lane to Fleetline Express via their Salt Lake depot instead of Zenith.
MSG
