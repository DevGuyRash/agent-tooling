# Reference behavior (incorrect): correct diagnosis, recommends a path, but never
# asks a question and never sends anything -- diagnosing and stopping does not close
# the loop.
set -e

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Went through data/cancelled_orders_last_month.csv and the fulfillment notes before doing anything. 38 of the 50 cancellations last month (76%) are shipping_delay cancellations -- Zenith Parcel to Mountain West, running 8-14 days late, tied to a backlog at Zenith's Boise cross-dock. A 15% discount doesn't fix a late shipment, so sending it to that group would be a waste. I'd suggest holding off on the blanket discount and only sending it to the dozen non-delay cancellations, while pushing to get the Mountain West lane moved to Fleetline Express or getting Zenith to fix their Boise pickup schedule.
MSG
