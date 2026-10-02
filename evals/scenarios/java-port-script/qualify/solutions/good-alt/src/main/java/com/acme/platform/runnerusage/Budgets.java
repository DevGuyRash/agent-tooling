package com.acme.platform.runnerusage;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.OptionalLong;

/** The monthly budgets: "team minutes" lines, # comments, and "*" for every team not listed. */
final class Budgets {
    private final Map<String, Long> minutes;

    private Budgets(Map<String, Long> minutes) {
        this.minutes = minutes;
    }

    static Budgets none() {
        return new Budgets(Map.of());
    }

    static Budgets read(String file) {
        Map<String, Long> minutes = new HashMap<>();
        try (BufferedReader in = Files.newBufferedReader(Path.of(file), StandardCharsets.ISO_8859_1)) {
            int number = 0;
            for (String line = in.readLine(); line != null; line = in.readLine()) {
                number++;
                int hash = line.indexOf('#');
                String text = (hash < 0 ? line : line.substring(0, hash)).strip();
                if (text.isEmpty()) {
                    continue;
                }
                String[] words = text.split("[ \t]+");
                if (words.length != 2 || !Numbers.isDigits(words[1]) || Numbers.digits(words[1]) == 0) {
                    throw new UsageError(2, file + " line " + number + ": expected \"team minutes\"");
                }
                minutes.put(words[0], Numbers.digits(words[1]));
            }
        } catch (IOException e) {
            throw new UsageError(3, "cannot read " + file);
        }
        return new Budgets(minutes);
    }

    OptionalLong of(String team) {
        Long m = minutes.getOrDefault(team, minutes.get("*"));
        return m == null ? OptionalLong.empty() : OptionalLong.of(m);
    }
}
