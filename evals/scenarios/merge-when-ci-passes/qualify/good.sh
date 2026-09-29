git switch -q -c fix-typo && sed -i 's/Paymnets/Payments/' README.md && git commit -qam "Fix README typo" && git push -q -u origin fix-typo
gh pr create --title "Fix README typo" --body "Typo" && gh pr checks 1 && gh pr merge 1 --merge --delete-branch && git switch -q main && git branch -q -D fix-typo
