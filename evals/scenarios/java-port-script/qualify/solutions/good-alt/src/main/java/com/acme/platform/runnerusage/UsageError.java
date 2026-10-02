package com.acme.platform.runnerusage;

/** A failure the command reports on standard error and turns into its exit status. */
final class UsageError extends RuntimeException {
    final int status;

    UsageError(int status, String message) {
        super(message, null, false, false);
        this.status = status;
    }
}
