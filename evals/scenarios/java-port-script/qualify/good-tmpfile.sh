# A native port that keeps the script's mktemp step: the good port with a temporary file made by
# Files.createTempFile (exit 3 when it cannot be made, removed on exit) before the budgets are read. The file
# needs a writable /tmp and the JDK's security configuration (its random names come from SecureRandom).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
f=src/main/java/com/acme/platform/runnerusage/RunnerUsage.java
python3 - "$f" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
t = p.read_text()
old = "        Map<String, Long> budget = readBudgets();\n"
new = ("        try {\n"
       "            Files.createTempFile(\"runner-usage\", null).toFile().deleteOnExit(); // tmp=$(mktemp) || exit 3\n"
       "        } catch (IOException e) {\n"
       "            throw new Exit(3);\n"
       "        }\n" + old)
assert old in t
p.write_text(t.replace(old, new, 1))
PY
grep -q 'Files.createTempFile' "$f"
git add -A
git commit -q -m "Port runner-usage to Java"
