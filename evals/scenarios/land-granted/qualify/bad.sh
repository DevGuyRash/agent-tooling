git switch -q -c fix && sed -i 's/Paymnets/Payments/' README.md && git commit -qam "Fix typo" && git push -q -u origin fix && gh pr create --title t --body b
