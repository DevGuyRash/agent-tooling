## Friction diagnostics

WHEN any error, failure, unexpected outcome, or friction of any kind occurs THEN you SHALL log it using the `friction-diagnostics` skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT add a duplicate entry.

Filing requires two commands. The event is not complete until both have run.

1. **`report-friction.sh`** — writes the event, outputs the event ID + existing tags
2. **`report-friction.sh --add-tags`** — tags the event using the ID from command 1

**Command 1 — report.** You SHALL:
- Write `action_taken` as three sentences: (1) what you read or consulted before acting and where, (2) the exact command or code you executed with arguments, (3) what you observed before and during the failure.
  - Bad: `"Ran the script and it was not there."`
  - Good: `"I read AGENTS.md line 18 which directed me to run scripts/ci-check.sh. I ran rg --files scripts to search for it. The file was not present in the listing."`
- Write `interpretation` as three sentences: (1) the meaning you assigned to the source material — quote the specific wording, (2) why that reading was reasonable, (3) what the mismatch reveals.
  - Bad: `"The instructions seemed wrong."`
  - Good: `"The instruction says 'Run scripts/ci-check.sh' in imperative form with no caveats. Imperative paths normally refer to existing files. Its absence reveals a documentation gap."`
- Write `actual_outcome` with the exact error message, exit code, or output verbatim. Do not paraphrase.
- Write `expected_outcome` with the specific behavior you anticipated and which source you derived it from.
- Write `instruction_text` as the exact text you acted on, quoted verbatim.
- Populate `sources` with typed references when the friction can be localized.

**Command 2 — tag.** The output from command 1 shows existing tags and the exact `--add-tags` invocation. You SHALL:
- Run the `--add-tags` command shown in the output.
- Select relevant tags from the existing vocabulary shown.
- Create new tags for any dimension not covered (tool, language, component, failure pattern, domain).
- Prefer more tags over fewer.
