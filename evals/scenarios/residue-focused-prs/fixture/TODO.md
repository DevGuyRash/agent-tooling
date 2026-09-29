# Monitoring cleanup

- alerts.yml: the `DiskAlmostFull` alert fires at 50%; it should fire at 90%.
- alerts.yml: the `HighLatency` alert has a typo in its summary ("latncy").
- scrape.yml: the `node` job still scrapes the decommissioned host `old-db:9100`; remove it.
