package com.acme.platform.runnerusage;

import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * CI runner minutes per team from the CI job export, against the monthly budgets.
 *
 * <pre>
 *   runner-usage [-b BUDGETS] [-m YYYY-MM] [-p POOL]... [-n N] [FILE...]
 * </pre>
 *
 * A port of scripts/runner-usage.sh with the same output, flags, and exit statuses: 0, or 1 when any team is over
 * its budget, 2 for a usage error or a bad budgets line, 3 when an input or the budgets file cannot be read.
 */
public final class RunnerUsage {
    private static final String PROG = "runner-usage";
    private static final Pattern MONTH = Pattern.compile("[0-9]{4}-[01][0-9]");
    private static final Pattern POOL = Pattern.compile("[a-z0-9-]+");
    private static final Pattern DIGITS = Pattern.compile("[0-9]+");
    private static final Pattern TEAM = Pattern.compile("[a-z][a-z0-9-]*");
    private static final Pattern DATE = Pattern.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}");
    private static final Pattern BLANKS = Pattern.compile("[ \t\n]+");

    /** Exits the program with a status, after its message has been written. */
    private static final class Exit extends Exception {
        final int status;

        Exit(int status) {
            super(null, null, false, false);
            this.status = status;
        }
    }

    private static final class Team {
        final String name;
        long jobs;
        long failed;
        long minutes;
        long budget;

        Team(String name) {
            this.name = name;
        }
    }

    private final PrintStream out;
    private final PrintStream err;
    private String budgets;
    private String month;
    private final Set<String> pools = new HashSet<>();
    private long top;
    private long skipped;

    private RunnerUsage(PrintStream out, PrintStream err) {
        this.out = out;
        this.err = err;
    }

    public static void main(String[] args) {
        PrintStream out = new PrintStream(new java.io.FileOutputStream(java.io.FileDescriptor.out), false,
                StandardCharsets.ISO_8859_1);
        PrintStream err = new PrintStream(new java.io.FileOutputStream(java.io.FileDescriptor.err), true,
                StandardCharsets.ISO_8859_1);
        int status;
        try {
            status = new RunnerUsage(out, err).run(args);
        } catch (Exit e) {
            status = e.status;
        }
        out.flush();
        System.exit(status);
    }

    private Exit usage() {
        err.println("usage: " + PROG + " [-b BUDGETS] [-m YYYY-MM] [-p POOL]... [-n N] [FILE...]");
        return new Exit(2);
    }

    private Exit fail(int status, String message) {
        err.println(PROG + ": " + message);
        return new Exit(status);
    }

    /** Options as getopts reads "b:m:p:n:": clustered, values attached or in the next word, "--" ends them. */
    private int options(String[] args) throws Exit {
        int i = 0;
        while (i < args.length) {
            String arg = args[i];
            if (arg.equals("--")) {
                return i + 1;
            }
            if (arg.length() < 2 || arg.charAt(0) != '-') {
                return i;
            }
            i++;
            for (int j = 1; j < arg.length(); j++) {
                char opt = arg.charAt(j);
                if ("bmpn".indexOf(opt) < 0) {
                    err.println(PROG + ": illegal option -- " + opt);
                    throw usage();
                }
                String value;
                if (j + 1 < arg.length()) {
                    value = arg.substring(j + 1);
                } else if (i < args.length) {
                    value = args[i++];
                } else {
                    err.println(PROG + ": option requires an argument -- " + opt);
                    throw usage();
                }
                option(opt, value);
                break;
            }
        }
        return i;
    }

    private void option(char opt, String value) throws Exit {
        switch (opt) {
            case 'b' -> budgets = value;
            case 'm' -> {
                if (!MONTH.matcher(value).matches()) {
                    throw fail(2, "-m wants YYYY-MM, got '" + value + "'");
                }
                month = value;
            }
            case 'p' -> {
                if (!POOL.matcher(value).matches()) {
                    throw fail(2, "bad pool name '" + value + "'");
                }
                pools.add(value);
            }
            default -> {
                if (!DIGITS.matcher(value).matches()) {
                    throw fail(2, "-n wants a number, got '" + value + "'");
                }
                top = parseCount(value);
            }
        }
    }

    /** A string of digits as a number, capped where a long ends. */
    private static long parseCount(String digits) {
        try {
            return Long.parseLong(digits);
        } catch (NumberFormatException e) {
            return Long.MAX_VALUE;
        }
    }

    private int run(String[] args) throws Exit {
        int first = options(args);
        List<String> files = new ArrayList<>();
        for (int i = first; i < args.length; i++) {
            files.add(args[i]);
        }
        List<String> readable = new ArrayList<>();
        if (budgets != null && !budgets.isEmpty()) {
            readable.add(budgets);
        }
        readable.addAll(files);
        for (String f : readable) {
            Path p = Path.of(f);
            if (!Files.isRegularFile(p) || !Files.isReadable(p)) {
                throw fail(3, "cannot read " + f);
            }
        }
        Map<String, Long> budget = readBudgets();
        Map<String, Team> teams = new HashMap<>();
        if (files.isEmpty()) {
            tally(lines(System.in), teams);
        } else {
            for (String f : files) {
                try (InputStream in = Files.newInputStream(Path.of(f))) {
                    tally(lines(in), teams);
                } catch (IOException e) {
                    throw fail(3, "cannot read " + f);
                }
            }
        }
        if (skipped > 0) {
            err.println(PROG + ": skipped " + skipped + " malformed " + (skipped == 1 ? "line" : "lines"));
        }
        List<Team> rows = new ArrayList<>(teams.values());
        for (Team t : rows) {
            Long b = budget.containsKey(t.name) ? budget.get(t.name) : budget.get("*");
            t.budget = b == null ? 0 : b;
        }
        rows.sort((a, b) -> a.minutes != b.minutes ? Long.compare(b.minutes, a.minutes) : a.name.compareTo(b.name));
        return report(rows);
    }

    private Map<String, Long> readBudgets() throws Exit {
        Map<String, Long> budget = new HashMap<>();
        if (budgets == null || budgets.isEmpty()) {
            return budget;
        }
        List<String> lines;
        try (InputStream in = Files.newInputStream(Path.of(budgets))) {
            lines = lines(in);
        } catch (IOException e) {
            throw fail(3, "cannot read " + budgets);
        }
        int number = 0;
        for (String line : lines) {
            number++;
            int hash = line.indexOf('#');
            if (hash >= 0) {
                line = line.substring(0, hash);
            }
            String trimmed = line.replaceAll("^[ \t\n]+|[ \t\n]+$", "");
            if (trimmed.isEmpty()) {
                continue;
            }
            String[] words = BLANKS.split(trimmed);
            if (words.length != 2 || !DIGITS.matcher(words[1]).matches() || parseCount(words[1]) == 0) {
                throw fail(2, budgets + " line " + number + ": expected \"team minutes\"");
            }
            budget.put(words[0], parseCount(words[1]));
        }
        return budget;
    }

    /** The records of a stream as awk reads them: split on newlines, a last line without one kept. */
    private static List<String> lines(InputStream in) throws Exit {
        byte[] data;
        try {
            data = in.readAllBytes();
        } catch (IOException e) {
            throw new Exit(3);
        }
        String text = new String(data, StandardCharsets.ISO_8859_1);
        List<String> lines = new ArrayList<>();
        int start = 0;
        while (start < text.length()) {
            int nl = text.indexOf('\n', start);
            if (nl < 0) {
                lines.add(text.substring(start));
                break;
            }
            lines.add(text.substring(start, nl));
            start = nl + 1;
        }
        return lines;
    }

    private void tally(List<String> lines, Map<String, Team> teams) {
        boolean firstLine = true;
        for (String line : lines) {
            String[] f = line.isEmpty() ? new String[0] : line.split(",", -1);
            boolean header = firstLine && f.length > 0 && f[0].equals("job_id");
            firstLine = false;
            if (header) {
                continue;
            }
            if (f.length != 6 || !TEAM.matcher(f[1]).matches() || f[2].isEmpty() || !DATE.matcher(f[3]).matches()
                    || !DIGITS.matcher(f[4]).matches()
                    || !(f[5].equals("success") || f[5].equals("failed") || f[5].equals("canceled"))) {
                skipped++;
                continue;
            }
            if (month != null && !f[3].substring(0, 7).equals(month)) {
                continue;
            }
            if (!pools.isEmpty() && !pools.contains(f[2])) {
                continue;
            }
            long seconds = parseCount(f[4]);
            long minutes = Math.max(1, (seconds + 59) / 60);
            Team t = teams.computeIfAbsent(f[1], Team::new);
            t.jobs++;
            t.minutes += minutes;
            if (f[5].equals("failed")) {
                t.failed++;
            }
        }
    }

    private int report(List<Team> rows) {
        out.printf("%-16s %6s %7s %9s %7s %6s\n", "TEAM", "JOBS", "FAILED", "MINUTES", "BUDGET", "USED");
        long jobs = 0, failed = 0, minutes = 0;
        long shown = 0;
        boolean anyOver = false;
        for (Team t : rows) {
            shown++;
            jobs += t.jobs;
            failed += t.failed;
            minutes += t.minutes;
            boolean over = t.budget > 0 && t.minutes > t.budget;
            anyOver |= over;
            if (top > 0 && shown > top) {
                continue;
            }
            String b = t.budget > 0 ? Long.toString(t.budget) : "-";
            String used = t.budget > 0 ? (t.minutes * 100 / t.budget) + "%" : "-";
            out.printf("%-16.16s %6d %7d %9d %7s %6s%s\n", t.name, t.jobs, t.failed, t.minutes, b, used,
                    over ? " !" : "");
        }
        if (top > 0 && shown > top) {
            long more = shown - top;
            out.printf("... and %d more %s\n", more, more == 1 ? "team" : "teams");
        }
        out.printf("%-16s %6d %7d %9d\n", "TOTAL", jobs, failed, minutes);
        return anyOver ? 1 : 0;
    }
}
