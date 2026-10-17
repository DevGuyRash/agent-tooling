# The same repository, history and task as heal-autolaunch-recurring, built by its setup script and from its fixture,
# with the store of open observations empty: the first time anyone meets the stale line. Only that differs.
set -e
HEAL_AUTOLAUNCH_SRC="$(cd "$(dirname "$0")/../heal-autolaunch-recurring" && pwd)"
HEAL_AUTOLAUNCH_OBSERVED=no
export HEAL_AUTOLAUNCH_SRC HEAL_AUTOLAUNCH_OBSERVED
cp -R "$HEAL_AUTOLAUNCH_SRC/fixture/." .
. "$HEAL_AUTOLAUNCH_SRC/setup.sh"
