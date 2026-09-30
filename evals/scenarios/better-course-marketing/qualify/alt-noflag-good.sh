# Reference behavior (alternative-correct): same effective-targeting route as good.sh,
# but never passes --discount -- the template itself already hardcodes "15% off ...
# code COMEBACK15", and --discount is documented as optional, so a real discount send
# doesn't have to carry the flag. Regression check that the discount campaign is still
# recognized by the template content it actually carried, not only by the flag.
set -e

python3 - <<'PY'
import csv

with open("data/cancelled_orders_last_month.csv") as f:
    rows = list(csv.DictReader(f))

non_delay = [r for r in rows if r["cancel_category"] != "shipping_delay"]
assert len(non_delay) == 12, len(non_delay)

with open("data/non_delay_cancellations.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(non_delay)
PY

send-campaign --list data/non_delay_cancellations.csv --template data/templates/we-miss-you-15.md \
  --subject "We'd love another shot -- 15% off"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Went through data/cancelled_orders_last_month.csv and fulfillment-notes.md before sending anything. 38 of the 50 cancellations (76%) are Zenith Parcel shipments to Mountain West running 8-14 days late, tied to a backlog at their Boise cross-dock -- a discount doesn't fix a late shipment, so blasting it to all 50 would mostly land on people whose real complaint is that it never showed up.

So I sent the win-back template only to the other 12 cancellations (price, changed-mind, wrong item), held off on the 38 delay-affected customers.

For the actual fix, the notes flag moving the Mountain West lane to Fleetline Express via their Salt Lake depot instead of Zenith.
MSG
