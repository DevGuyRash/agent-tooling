# Adds the pursuit command to the README's command list (shared by the qualification scripts).
set -e
sed -i 's/^startline sequence START \[--starts N\] \[--gap MIN\]  signal times for one start or several in a row$/&\nstartline pursuit [--minutes N] FILE               pursuit-race start times by class (docs\/pursuit.md)/' README.md
grep -q '^startline pursuit' README.md
