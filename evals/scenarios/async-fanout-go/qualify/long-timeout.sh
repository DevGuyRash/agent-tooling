# Wrong (must fail failures_handled): good.sh with 10 seconds before an inverter counts as not answering, not
# the ticket's 2. It still finishes within the budget, but an inverter that answers after 3 to 6 seconds is
# printed as a reading instead of `no answer`.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/noAnswerAfter    = 2 \* time.Second /noAnswerAfter    = 10 * time.Second /' cmd/farmctl/yield.go
grep -q 'noAnswerAfter    = 10 \* time.Second ' cmd/farmctl/yield.go
git commit -q -am "farmctl yield: give slow inverters longer"
