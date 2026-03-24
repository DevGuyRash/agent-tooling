## Friction diagnostics
You SHALL initialize the `friction-diagnostics` skill at the start of every task, before substantive work begins. This is mandatory, not conditional.
WHEN any error, failure, unexpected outcome, code bug, test failure, compilation error, runtime exception, or friction of any kind occurs THEN you SHALL immediately log it using the `friction-diagnostics` skill. There is no threshold for "important enough to log" — if it went wrong, log it.
WHEN the same issue repeats without materially new evidence, THEN you SHALL NOT create a duplicate entry.
