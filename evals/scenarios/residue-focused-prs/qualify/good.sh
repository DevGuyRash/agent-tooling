git switch -q -c monitoring-cleanup
sed -i 's/disk_used_ratio > 0.5/disk_used_ratio > 0.9/; s/latncy/latency/' alerts.yml
sed -i 's/, "old-db:9100"//' scrape.yml
git commit -qam "Clean up monitoring config" && git push -q -u origin monitoring-cleanup && gh pr create --title "Monitoring cleanup" --body "TODO items"
