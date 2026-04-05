## Friction diagnostics

WHEN any error, failure, unexpected outcome, or friction of any kind occurs THEN you SHALL log it using the `friction-diagnostics` skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT add a duplicate entry.

Filing is a single command. You SHALL provide:

- **`--reading`** — your full first-person account: what you consulted, what you did, what you observed, how you interpreted it, and why you made the decisions you made.
- **`--actual-outcome`** — the verbatim error message, exit code, or output. Do not paraphrase.
- **`--expected-outcome`** — what you expected to happen and why.
- **`--impact`** — `blocked`, `degraded`, `noisy`, or `continued`.
- **`--source-ref`** and **`--source-type`** — where the friction originated.
- **`--tags`** — specific labels (e.g., `git-signing,ssh-auth-sock`).
- **`--aliases`** — broader groupings (e.g., `auth,git`).

WHEN the friction can be localized to a specific file THEN you SHALL populate the `sources` array with file path and line range.
WHEN text from multiple sources shaped the action THEN you SHALL use `--from-json -` with a `sources` array containing multiple entries.
