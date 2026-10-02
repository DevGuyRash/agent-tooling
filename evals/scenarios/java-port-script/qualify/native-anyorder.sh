# Native but wrong: the good port with options read anywhere on the command line, as GNU getopt permutes them,
# instead of stopping at the first operand as getopts does. `FILE -n 1` then prints one team instead of failing
# with "cannot read -n" (exit 3). The fixture's own cases put every option first, so only the hidden cases catch it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
f=src/main/java/com/acme/platform/runnerusage/RunnerUsage.java
python3 - "$f" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
t = p.read_text()
edits = [
    ("    private long skipped;\n", "    private long skipped;\n    private final List<String> operands = new ArrayList<>();\n"),
    ("            if (arg.equals(\"--\")) {\n                return i + 1;\n            }\n"
     "            if (arg.length() < 2 || arg.charAt(0) != '-') {\n                return i;\n            }\n",
     "            if (arg.equals(\"--\")) {\n                operands.addAll(List.of(args).subList(i + 1, args.length));\n"
     "                return args.length;\n            }\n"
     "            if (arg.length() < 2 || arg.charAt(0) != '-') {\n                operands.add(arg);\n"
     "                i++;\n                continue;\n            }\n"),
    ("        for (int i = first; i < args.length; i++) {\n            files.add(args[i]);\n        }\n",
     "        files.addAll(operands);\n"),
]
for old, new in edits:
    assert t.count(old) == 1, old
    t = t.replace(old, new)
p.write_text(t)
PY
grep -q 'operands.add(arg);' "$f"
git add -A
git commit -q -m "Port runner-usage to Java"
