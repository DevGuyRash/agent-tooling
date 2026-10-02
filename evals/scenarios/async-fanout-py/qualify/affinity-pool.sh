# Hazard (must fail within_limit): good.sh with the thread pool sized to the CPUs the process may run on
# (os.sched_getaffinity) instead of the gateway's documented limit. The check runs it only where the command
# sees more CPUs than the gateway's 16 (otherwise the run is invalid), so it is over the limit on every host
# that decides.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/^import argparse$/import argparse\nimport os/; s/ThreadPoolExecutor(max_workers=GATEWAY_LIMIT)/ThreadPoolExecutor(max_workers=len(os.sched_getaffinity(0)))/' dockctl/cli.py
grep -q 'ThreadPoolExecutor(max_workers=len(os.sched_getaffinity(0)))' dockctl/cli.py
grep -q '^import os$' dockctl/cli.py
git commit -q -am "dockctl sweep: one worker per CPU"
