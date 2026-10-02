# bridge-helper.sh with the script found from the working directory (scripts/invoice.py), which works when hours
# runs from the repository root, as the README's node bin/hours.ts does. Fails the minimal root, which has the
# same repository and working directory but no python3, and starts_no_interpreter.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-helper/." .
sed -i "/^import { fileURLToPath } from 'node:url';$/d; s|^import { join } from 'node:path';$|import { join, resolve } from 'node:path';|; s|^const SCRIPT = fileURLToPath(new URL('../../scripts/invoice.py', import.meta.url));$|const SCRIPT = resolve('scripts', 'invoice.py');|" \
	src/commands/invoice.ts
grep -q "^const SCRIPT = resolve('scripts', 'invoice.py');$" src/commands/invoice.ts
if grep -q 'fileURLToPath' src/commands/invoice.ts; then exit 1; fi
git add -A
git commit -q -m "hours invoice: bill one client's time for a month or a range of dates"
