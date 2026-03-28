## Friction diagnostics
WHEN any error, failure, unexpected outcome, code bug, test failure, compilation error, runtime exception, or friction of any kind occurs THEN you SHALL immediately log it using the `friction-diagnostics` skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT create a duplicate entry.
WHEN friction is logged THEN you SHALL use the canonical repo-scoped `events.jsonl` target unless an explicit `--events-file` path is required.
WHEN the friction can be localized to a specific file, document, or URL THEN you SHALL populate the `sources` array in the event.
WHEN reading prior friction THEN you SHOULD start with tool-managed `INDEX.md`, then use `query-friction.*`, and only then read raw `events.jsonl` or `jq` for a custom slice.
WHEN writing `action_taken` THEN you SHALL write a multi-sentence first-person account: quote the exact command or tool call you ran, the arguments you passed, and describe what you observed before and during the failure. You SHALL NOT write a single-sentence summary.
WHEN writing `actual_outcome` THEN you SHALL include the exact error message, exit code, or stderr output verbatim. Do not paraphrase the error.
WHEN writing `interpretation` THEN you SHALL write at least three sentences: (1) the precise meaning you assigned to the source material at the time you acted, (2) the specific wording, code, or phrasing that produced that reading — quote it, and (3) the reasoning chain that made that reading seem correct given what you knew. You SHALL NOT compress this into one sentence.
WHEN writing `expected_outcome` THEN you SHALL state the specific behavior you anticipated and identify which instruction, documentation, code, or configuration you derived it from.
WHEN writing `instruction_text` THEN you SHALL quote the exact text you acted on verbatim — whether a written instruction, code snippet, function signature, config value, error message, or documentation fragment.
