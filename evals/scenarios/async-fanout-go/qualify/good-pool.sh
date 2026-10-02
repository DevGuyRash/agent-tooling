# Alternative correct approach (must pass): a new survey package with its own dialing and parsing, twelve
# worker goroutines (under the gateway's 16) pulling from a jobs channel, and a context per read whose
# end closes the connection (context.AfterFunc).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-pool/." .
git add -A
git commit -q -m "farmctl yield"
