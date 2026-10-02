package com.acme.platform.runnerusage;

import java.io.BufferedReader;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.OptionalLong;

/**
 * runner-usage: CI runner minutes per team from the CI job export, against the monthly budgets. Same output, flags,
 * and exit statuses as scripts/runner-usage.sh.
 */
public final class RunnerUsage {
    private RunnerUsage() {
    }

    public static void main(String[] args) {
        PrintStream out = new PrintStream(new FileOutputStream(FileDescriptor.out), false, StandardCharsets.ISO_8859_1);
        int status;
        try {
            status = run(args, out);
        } catch (UsageError e) {
            for (String line : e.getMessage().split("\n")) {
                System.err.println(line.startsWith("usage:") ? line : "runner-usage: " + line);
            }
            status = e.status;
        }
        out.flush();
        System.exit(status);
    }

    static int run(String[] args, PrintStream out) {
        Options options = Options.parse(args);
        options.budgets().ifPresent(RunnerUsage::mustRead);
        options.files().forEach(RunnerUsage::mustRead);
        Budgets budgets = options.budgets().map(Budgets::read).orElse(Budgets.none());
        Ledger ledger = new Ledger(options);
        try {
            if (options.files().isEmpty()) {
                ledger.read(new BufferedReader(new InputStreamReader(System.in, StandardCharsets.ISO_8859_1)));
            } else {
                for (String file : options.files()) {
                    try (BufferedReader in = Files.newBufferedReader(Path.of(file), StandardCharsets.ISO_8859_1)) {
                        ledger.read(in);
                    }
                }
            }
        } catch (IOException e) {
            throw new UsageError(3, "cannot read input: " + e.getMessage());
        }
        if (ledger.malformed() > 0) {
            System.err.printf("runner-usage: skipped %d malformed %s%n", ledger.malformed(),
                    ledger.malformed() == 1 ? "line" : "lines");
        }
        List<Ledger.Usage> rows = ledger.teams().stream()
                .sorted(Comparator.comparingLong(Ledger.Usage::minutes).reversed())
                .toList();
        return print(rows, budgets, options.top(), out);
    }

    private static void mustRead(String file) {
        Path p = Path.of(file);
        if (!Files.isRegularFile(p) || !Files.isReadable(p)) {
            throw new UsageError(3, "cannot read " + file);
        }
    }

    private static int print(List<Ledger.Usage> rows, Budgets budgets, long top, PrintStream out) {
        StringBuilder table = new StringBuilder(String.format("%-16s %6s %7s %9s %7s %6s%n", "TEAM", "JOBS",
                "FAILED", "MINUTES", "BUDGET", "USED").replace(System.lineSeparator(), "\n"));
        boolean over = false;
        long jobs = 0, failed = 0, minutes = 0;
        for (int i = 0; i < rows.size(); i++) {
            Ledger.Usage u = rows.get(i);
            jobs += u.jobs();
            failed += u.failed();
            minutes += u.minutes();
            OptionalLong budget = budgets.of(u.team());
            boolean exceeded = budget.isPresent() && u.minutes() > budget.getAsLong();
            over |= exceeded;
            if (top > 0 && i >= top) {
                continue;
            }
            String name = u.team().length() > 16 ? u.team().substring(0, 16) : u.team();
            table.append(String.format("%-16s %6d %7d %9d %7s %6s%s", name, u.jobs(), u.failed(), u.minutes(),
                    budget.isPresent() ? String.valueOf(budget.getAsLong()) : "-",
                    budget.isPresent() ? u.minutes() * 100 / budget.getAsLong() + "%" : "-",
                    exceeded ? " !" : "")).append('\n');
        }
        if (top > 0 && rows.size() > top) {
            long more = rows.size() - top;
            table.append("... and ").append(more).append(more == 1 ? " more team\n" : " more teams\n");
        }
        table.append(String.format("%-16s %6d %7d %9d", "TOTAL", jobs, failed, minutes)).append('\n');
        out.print(table);
        return over ? 1 : 0;
    }
}
