package com.acme.platform.runnerusage;

final class Numbers {
    private Numbers() {
    }

    /** A run of ASCII digits as a number; a run too long for a long is the largest long. */
    static long digits(String s) {
        long n = 0;
        for (int i = 0; i < s.length(); i++) {
            int d = s.charAt(i) - '0';
            if (n > (Long.MAX_VALUE - d) / 10) {
                return Long.MAX_VALUE;
            }
            n = n * 10 + d;
        }
        return n;
    }

    static boolean isDigits(String s) {
        if (s.isEmpty()) {
            return false;
        }
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c < '0' || c > '9') {
                return false;
            }
        }
        return true;
    }
}
