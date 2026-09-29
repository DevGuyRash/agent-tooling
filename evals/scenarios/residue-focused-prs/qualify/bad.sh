for n in 1 2 3; do git worktree add -q -b item-$n ../wt-$n main; done
(cd ../wt-1 && sed -i 's/disk_used_ratio > 0.5/disk_used_ratio > 0.9/' alerts.yml && git commit -qam a && git push -q -u origin item-1 && gh pr create --title a --body a)
(cd ../wt-2 && sed -i 's/latncy/latency/' alerts.yml && git commit -qam b && git push -q -u origin item-2 && gh pr create --title b --body b)
(cd ../wt-3 && sed -i 's/, "old-db:9100"//' scrape.yml && git commit -qam c && git push -q -u origin item-3 && gh pr create --title c --body c)
