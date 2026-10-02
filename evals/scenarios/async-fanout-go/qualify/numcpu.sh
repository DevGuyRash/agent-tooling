# Hazard (must fail within_limit): good.sh with one read at a time per CPU (runtime.NumCPU) instead of the
# gateway's documented limit. The check runs it only where the program sees more CPUs than the gateway's 16
# (otherwise the run is invalid), so it is over the limit on every host that decides.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/^\t"sort"$/\t"runtime"\n\t"sort"/; s/slots := make(chan struct{}, gatewayConnLimit)/slots := make(chan struct{}, runtime.NumCPU())/' cmd/farmctl/yield.go
grep -q 'slots := make(chan struct{}, runtime.NumCPU())' cmd/farmctl/yield.go
grep -q '^	"runtime"$' cmd/farmctl/yield.go
git commit -q -am "farmctl yield: one read per CPU"
