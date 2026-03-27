## Friction diagnostics
WHEN any error, failure, unexpected outcome, code bug, test failure, compilation error, runtime exception, or friction of any kind occurs THEN you SHALL immediately log it using the `friction-diagnostics` skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT create a duplicate entry.
WHEN friction is logged THEN you SHALL use the canonical repo-scoped `events.jsonl` target unless an explicit `--events-file` path is required.
WHEN reading prior friction THEN you SHOULD start with tool-managed `INDEX.md`, then use `query-friction.*`, and only then read raw `events.jsonl` or `jq` for a custom slice.
