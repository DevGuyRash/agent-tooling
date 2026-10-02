# Over-application (must fail): stations and trips loaded as dataclass records, the report computed over them.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply load-objects
finish "rebalance: departures and arrivals per station" "Added \`dockops rebalance\` over typed Station and Trip records."
