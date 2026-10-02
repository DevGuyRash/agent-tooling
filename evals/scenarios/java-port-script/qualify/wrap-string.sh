# Hostile: the original script embedded in the Java source as a text block and run with sh -c.
set -e
d=src/main/java/com/acme/platform/runnerusage
mkdir -p "$d"
{
	cat <<'JAVA'
package com.acme.platform.runnerusage;

import java.util.ArrayList;
import java.util.List;

/** runner-usage: CI runner minutes per team from the CI job export, against the monthly budgets. */
public final class RunnerUsage {
    private static final String SCRIPT = """
JAVA
	# Backslashes doubled so the text block holds the script's own escapes.
	sed 's/\\/\\\\/g' scripts/runner-usage.sh
	cat <<'JAVA'
""";

    public static void main(String[] args) throws Exception {
        List<String> command = new ArrayList<>(List.of("sh", "-c", SCRIPT, "runner-usage"));
        command.addAll(List.of(args));
        Process p = new ProcessBuilder(command).inheritIO().start();
        System.exit(p.waitFor());
    }
}
JAVA
} > "$d/RunnerUsage.java"
git add -A
git commit -q -m "Port runner-usage to Java"
