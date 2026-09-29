git switch -q -c fix-typo && sed -i 's/Paymnets/Payments/' README.md && git commit -qam "Fix README typo" && git push -q -u origin fix-typo && gh pr create --title t --body b
