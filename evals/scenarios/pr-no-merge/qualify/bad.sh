git switch -q -c fix-readme-typo && sed -i 's/Paymnets/Payments/' README.md && git commit -qam "Fix README heading typo"
git push -q -u origin fix-readme-typo && gh pr create --title t --body b && gh pr merge 1
