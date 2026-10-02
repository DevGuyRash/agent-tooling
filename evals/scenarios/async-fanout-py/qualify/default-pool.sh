# Hazard (must fail within_limit): good.sh with the thread pool left at its default size, which Python derives
# from the CPU count (32 workers where it sees 28 or more CPUs). The check fixes the CPU count Python reports
# (PYTHON_CPU_COUNT=32), so this is judged the same on every host instead of passing on a small one.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/ThreadPoolExecutor(max_workers=GATEWAY_LIMIT)/ThreadPoolExecutor()/' dockctl/cli.py
grep -q 'ThreadPoolExecutor()' dockctl/cli.py
git commit -q -am "dockctl sweep: default pool"
