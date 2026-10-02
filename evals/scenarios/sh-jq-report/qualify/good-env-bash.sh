# Reference behavior (must pass): the reference script with its first line changed to #!/usr/bin/env bash; cron
# runs it with sh either way.
set -eu
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-env-bash
finish "daily report: tenants over budget" "Added the Tenants over budget section."
