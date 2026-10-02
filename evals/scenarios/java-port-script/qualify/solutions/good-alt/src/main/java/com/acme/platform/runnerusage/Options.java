package com.acme.platform.runnerusage;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/** The command line, read the way the shell script's getopts "b:m:p:n:" reads it. */
record Options(Optional<String> budgets, Optional<String> month, Set<String> pools, long top, List<String> files) {
    static final String USAGE = "usage: runner-usage [-b BUDGETS] [-m YYYY-MM] [-p POOL]... [-n N] [FILE...]";

    static Options parse(String[] args) {
        String budgets = null, month = null;
        Set<String> pools = new LinkedHashSet<>();
        long top = 0;
        int i = 0;
        scan:
        while (i < args.length) {
            String word = args[i];
            if (word.equals("--")) {
                i++;
                break;
            }
            if (!word.startsWith("-") || word.equals("-")) {
                break;
            }
            i++;
            for (int at = 1; at < word.length(); at++) {
                char flag = word.charAt(at);
                if (flag != 'b' && flag != 'm' && flag != 'p' && flag != 'n') {
                    throw new UsageError(2, "illegal option -- " + flag + "\n" + USAGE);
                }
                String value;
                if (at + 1 < word.length()) {
                    value = word.substring(at + 1);
                } else if (i < args.length) {
                    value = args[i++];
                } else {
                    throw new UsageError(2, "option requires an argument -- " + flag + "\n" + USAGE);
                }
                switch (flag) {
                    case 'b' -> budgets = value;
                    case 'm' -> {
                        if (!value.matches("\\d{4}-[01]\\d") || !value.chars().allMatch(c -> c < 128)) {
                            throw new UsageError(2, "-m wants YYYY-MM, got '" + value + "'");
                        }
                        month = value;
                    }
                    case 'p' -> {
                        if (value.isEmpty() || !value.chars().allMatch(c -> c == '-' || (c >= 'a' && c <= 'z')
                                || (c >= '0' && c <= '9'))) {
                            throw new UsageError(2, "bad pool name '" + value + "'");
                        }
                        pools.add(value);
                    }
                    default -> {
                        if (value.isEmpty() || !value.chars().allMatch(c -> c >= '0' && c <= '9')) {
                            throw new UsageError(2, "-n wants a number, got '" + value + "'");
                        }
                        top = Numbers.digits(value);
                    }
                }
                continue scan;
            }
        }
        List<String> files = new ArrayList<>(List.of(args).subList(i, args.length));
        return new Options(Optional.ofNullable(budgets).filter(b -> !b.isEmpty()), Optional.ofNullable(month),
                Set.copyOf(pools), top, files);
    }
}
