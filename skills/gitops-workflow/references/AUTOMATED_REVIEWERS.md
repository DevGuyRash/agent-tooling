# Automated reviewer feedback

Automated review bots are helpful but non-authoritative. Treat them like a well-meaning junior reviewer.

## Principles

1. **Verify before acting**
   - Bots can be outdated, wrong, or miss repo context.
2. **Respect repo invariants**
   - If a bot suggestion conflicts with conventions, security boundaries, or architecture, it’s wrong even if it sounds confident.
3. **Respond in the original thread**
   - Keep context together. Do not create a new top-level comment for a specific inline suggestion.
4. **Re-tag only when appropriate**
   - If you implemented the suggestion or you want re-checking, re-tag.
   - If you rejected the suggestion, do **not** re-tag; explain why.
5. **Use bots for low-risk wins**
   - Typos, obvious bugs, missing tests, style drift.
   - Be cautious with architectural changes.

## Optional trigger commands

Use these only if your repository has the corresponding bot enabled.
These are convenience triggers, not required workflow steps.
For Gemini full reviews, post slash commands in the PR Conversation tab (top-level comment), not inline diff threads.

- Codex:
  - `@codex review`
- Gemini Code Assist:
  - `/gemini review` (full structured review trigger in PR Conversation tab)
  - `/gemini summary` (high-level summary)
  - `/gemini help` (list commands)
  - `@gemini-code-assist <question>` (conversational follow-up)

Deterministic helper (preferred when posting a top-level re-review request):

- `bash "$SKILL_ROOT/scripts/pr-request-review.sh" <pr_number> [--repo owner/repo] [--note "<text>"]`

References:
- https://developers.google.com/gemini-code-assist/docs/review-github-code
- https://github.com/marketplace/gemini-code-assist

## If you cannot reply inline

If permissions/tooling prevent inline replies, leave a top-level PR comment referencing:
- the file path + line number (or thread URL)
- a short explanation of why inline reply was not possible
- what you changed (or why you declined)

## Common response snippets

Accepted:
- “Implemented this suggestion in `<file>`. Re-tagging for verification: @bot.”

Rejected:
- “Not applying this suggestion because it conflicts with `<invariant>`. Instead I did `<alternative>`.”

Needs clarification:
- “I’m not sure this applies here due to `<context>`. Can you clarify expected behavior?”
