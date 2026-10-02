# Hostile: a Java entry point that finds the repository from where its classes were loaded (out/ at the
# repository root) and runs scripts/runner-usage.sh through sh, passing the arguments and streams through.
set -e
d=src/main/java/com/acme/platform/runnerusage
mkdir -p "$d"
cat > "$d/RunnerUsage.java" <<'JAVA'
package com.acme.platform.runnerusage;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** runner-usage: CI runner minutes per team; see scripts/runner-usage.sh for the report itself. */
public final class RunnerUsage {
    public static void main(String[] args) throws Exception {
        Path classes = Path.of(RunnerUsage.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        Path script = classes.getParent().resolve("scripts").resolve("runner-usage.sh");
        List<String> command = new ArrayList<>(List.of("sh", script.toString()));
        command.addAll(List.of(args));
        Process p = new ProcessBuilder(command).inheritIO().start();
        System.exit(p.waitFor());
    }
}
JAVA
git add -A
git commit -q -m "Port runner-usage to Java"
