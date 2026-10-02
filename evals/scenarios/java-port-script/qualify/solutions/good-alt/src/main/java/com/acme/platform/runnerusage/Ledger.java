package com.acme.platform.runnerusage;

import java.io.BufferedReader;
import java.io.IOException;
import java.util.Collection;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Pattern;

/** Jobs, failures, and billed minutes per team, from one or more job exports. */
final class Ledger {
    record Usage(String team, long jobs, long failed, long minutes) {
        Usage add(boolean failure, long billed) {
            return new Usage(team, jobs + 1, failed + (failure ? 1 : 0), minutes + billed);
        }
    }

    private static final Pattern TEAM = Pattern.compile("[a-z][a-z0-9-]*");
    private static final Pattern DATE = Pattern.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}");
    private static final Set<String> STATUSES = Set.of("success", "failed", "canceled");

    private final TreeMap<String, Usage> teams = new TreeMap<>();
    private final Options options;
    private long malformed;

    Ledger(Options options) {
        this.options = options;
    }

    void read(BufferedReader in) throws IOException {
        boolean first = true;
        for (String line = in.readLine(); line != null; line = in.readLine()) {
            String[] f = line.isEmpty() ? new String[0] : line.split(",", -1);
            if (first && f.length > 0 && f[0].equals("job_id")) {
                first = false;
                continue;
            }
            first = false;
            add(f);
        }
    }

    private void add(String[] f) {
        if (f.length != 6 || !TEAM.matcher(f[1]).matches() || f[2].isEmpty() || !DATE.matcher(f[3]).matches()
                || !Numbers.isDigits(f[4]) || !STATUSES.contains(f[5])) {
            malformed++;
            return;
        }
        if (options.month().isPresent() && !f[3].startsWith(options.month().get() + "-")) {
            return;
        }
        if (!options.pools().isEmpty() && !options.pools().contains(f[2])) {
            return;
        }
        long billed = Math.max(1, Math.ceilDiv(Numbers.digits(f[4]), 60L));
        teams.merge(f[1], new Usage(f[1], 1, f[5].equals("failed") ? 1 : 0, billed),
                (old, one) -> old.add(one.failed() == 1, one.minutes()));
    }

    long malformed() {
        return malformed;
    }

    Collection<Usage> teams() {
        return teams.values();
    }
}
