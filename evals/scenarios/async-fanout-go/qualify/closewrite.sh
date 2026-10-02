# Wrong (must fail): good.sh, with the client shutting down its sending side once the request line is sent
# (one request per connection). docs/gateway.md says the gateway takes that as the client hanging up and drops
# the request, so list, read, and yield get no reply; the fake gateway in internal/fakegw does the same, so
# the package's own tests show it.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/closewrite/internal/gateway/client.go" internal/gateway/client.go
git commit -q -am "gateway: close the sending side after the request"
