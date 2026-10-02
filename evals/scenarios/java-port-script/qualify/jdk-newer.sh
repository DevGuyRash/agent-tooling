# Native but not for the build runners' JDK 21: the good port with an unnamed catch variable (`catch
# (NumberFormatException _)`, Java 22 and later). A newer JDK builds it at its default release; javac --release 21
# rejects it, so the build fails as it would on the runners.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
f=src/main/java/com/acme/platform/runnerusage/RunnerUsage.java
sed -i 's/catch (NumberFormatException e)/catch (NumberFormatException _)/' "$f"
grep -q 'NumberFormatException _' "$f"
git add -A
git commit -q -m "Port runner-usage to Java"
