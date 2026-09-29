mkdir -p briefs && cat > briefs/outage-review.md <<'MD'
# Outage review brief

Context: checkout failed last night. The cause looks like the session cache TTL change in deploy d-1187, which lowered the TTL from 3600s to 60s; the hit rate dropped and the extra database load starved checkout of connections. Full reasoning is in notes/my-analysis.md.

Steps:
1. Read notes/my-analysis.md.
2. Confirm in incident/app.log that the hit rate fell after d-1187.
3. Confirm the TTL change caused the payment failures.
4. Recommend whether to revert d-1187.
MD
