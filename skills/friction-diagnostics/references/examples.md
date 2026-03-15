# Examples

## Good entries

### Entry 1: Dispatch role slug mismatch

```markdown
## Entry 1: Dispatch role slug mismatch
**Recorded:** 2026-03-14 15:02:11 UTC
**Category:** skill/name-resolution/blocked
**Tags:** skill,name-resolution,blocked,dispatch,role,slug
**Instruction source:** SKILL.md:160
**Instruction text:** "Use `mpcr protocol dispatch --role <ROLE>` to get the domain-specific prompt."
**Action taken:** Ran `mpcr protocol dispatch --role architecture`.
**Expected outcome:** The CLI returns the architecture prompt.
**Actual outcome:** `error: unknown dispatch role: architecture`
**Interpretation:** I read the visible domain label as the role slug to pass to `--role`.
---
```

Why it is good:

- it preserves the exact chain of interpretation
- it records the expectation implied by the instruction
- it includes the observed failure text
- it does not propose a fix

### Entry 2: MCP search tool overpromises readable content

```markdown
## Entry 2: MCP search tool overpromises readable content
**Recorded:** 2026-03-14 15:04:33 UTC
**Category:** mcp/output-mismatch/degraded
**Tags:** mcp,output-mismatch,degraded,output
**Instruction source:** MCP tool description for `gmail_search`
**Instruction text:** "The tool description states it can 'search and read emails' — tool name: gmail_search"
**Action taken:** Called `gmail_search` with query `from:boss@company.com subject:quarterly review` expecting message bodies for summarization.
**Expected outcome:** Results containing message bodies or readable content, based on the tool description claiming read capability.
**Actual outcome:** Received 12 result objects each containing only: id, threadId, subject, from, date, and a 40-character snippet. No body content. The tool description promised readable bodies but the search operation returned metadata-only results.
**Interpretation:** I took "search and read" to mean the search tool returns readable content. It actually returns metadata-only results. A separate `gmail_get_message` call is needed per message for full bodies, but the tool description did not match what search alone delivers.
---
```

Why it is good:

- it captures the gap between the MCP tool description and actual behavior
- it includes what was returned (metadata-only) vs what was expected (bodies)
- the interpretation explains the reasoning chain: tool description → agent's assumption → mismatch
- it does not suggest the tool should be changed

### Entry 3: Ambiguous acceptance criteria in AGENTS.md

```markdown
## Entry 3: Ambiguous acceptance criteria in AGENTS.md
**Recorded:** 2026-03-14 15:09:02 UTC
**Category:** instructions/ambiguity/confusing
**Tags:** instructions,ambiguity,confusing,agents-md
**Instruction source:** AGENTS.md:34
**Instruction text:** "Keep the change minimal and production ready. The migration is optional if the feature works without it."
**Action taken:** Prepared a minimal patch and deferred the migration because the instruction called it optional.
**Expected outcome:** The instruction would settle whether the migration was in scope. "Optional" should mean the reviewer accepts the patch without it.
**Actual outcome:** The reviewer asked why the migration was not included and described the feature as incomplete. The instruction was ambiguous about whether "production ready" required the migration despite calling it optional. The acceptance boundary remained unclear.
**Interpretation:** I treated "minimal" as the dominant constraint and read "optional" at face value. The reviewer read "production ready" as requiring the migration. Both readings are defensible given the instruction text, which makes the instruction genuinely underspecified.
---
```

Why it is good:

- it quotes the specific AGENTS.md line including the ambiguous clause
- it records both sides of the interpretation conflict
- the interpretation explains why the agent chose one reading over the other
- it does not say which reading is correct

### Entry 4: Script crash from shell incompatibility

```markdown
## Entry 4: Script crash from shell incompatibility
**Recorded:** 2026-03-14 15:15:41 UTC
**Category:** script/crash/blocked
**Tags:** script,crash,blocked,posix-sh
**Instruction source:** README.md:22
**Instruction text:** "Run `scripts/verify.sh` to validate the build output."
**Action taken:** Ran `sh scripts/verify.sh` in the project container.
**Expected outcome:** The script validates build output and prints a pass/fail summary.
**Actual outcome:** The script crashed immediately on invocation with `scripts/verify.sh: 14: scripts/verify.sh: Syntax error: "(" unexpected` — a bash array syntax used on line 14 is not valid under dash. The container's `/bin/sh` links to dash, not bash.
**Interpretation:** I ran the script with `sh` as instructed. The script uses bash-specific syntax (arrays) but does not declare `#!/bin/bash` and the README does not mention bash as a requirement. The crash is a shell portability gap.
---
```

### Entry 5: Missing dependency in container environment

```markdown
## Entry 5: Missing dependency in container environment
**Recorded:** 2026-03-14 15:20:58 UTC
**Category:** environment/missing/blocked
**Tags:** environment,missing,blocked,dependency
**Instruction source:** Dockerfile comment on line 47
**Instruction text:** "Run the scanning step: `uv run scan.py`"
**Action taken:** Ran `uv run scan.py` inside the running container.
**Expected outcome:** The scan executes and produces results.
**Actual outcome:** `sh: uv: command not found` — exit code 127. The container image is Ubuntu 24.04 with Python 3.12 and pip installed, but uv is not found. The dependency on uv is not listed in the Dockerfile's package installation layer.
**Interpretation:** I followed the inline directive literally. The directive assumes uv is available, which is reasonable for local development but the container does not include it. The Dockerfile does not install uv and the compatibility notes do not mention it as a dependency.
---
```

### Entry 6: CLI flag contradicts actual behavior

```markdown
## Entry 6: CLI flag contradicts actual behavior
**Recorded:** 2026-03-14 15:28:14 UTC
**Category:** tool/contradiction/blocked
**Tags:** tool,contradiction,blocked,cli,output
**Instruction source:** CLI `--help` output for `lint-runner`
**Instruction text:** "The `--help` text lists `--format html` as a valid option: 'Output format: text, html, sarif (default: text)'"
**Action taken:** Ran `lint-runner --format html src/` to get browser-viewable lint results.
**Expected outcome:** Lint results printed as HTML based on the documented flag.
**Actual outcome:** `error: invalid value 'html' for '--format': valid values are text, sarif` — the CLI rejected the flag value that its own help text advertises. The help text does not match the actual accepted values.
**Interpretation:** I used the documented flag value from `--help`. The CLI's help text contradicts its actual behavior — it lists `html` as valid but only accepts `text` and `sarif` at execution time. The friction is a documented option that does not match docs, not a name-resolution failure.
---
```

**Calibration note:** With the current wording, the auto-categorizer already lands on `tool/contradiction/blocked`. If you wanted to emphasize steerability rather than hard failure for a similar case, the only plausible override would be the `impact` axis.

### Entry 7: Data contract uses wrong timestamp format

```markdown
## Entry 7: Data contract uses wrong timestamp format
**Recorded:** 2026-03-14 15:35:47 UTC
**Category:** data/schema/degraded
**Tags:** data,schema,degraded
**Instruction source:** `docs/data-contracts.md:18`
**Instruction text:** "All event records use the shared `EventRecord` structure. The `created_at` field contains the creation timestamp."
**Action taken:** Parsed the `created_at` value from a serialized event record, treating it as an ISO 8601 string for display formatting.
**Expected outcome:** The `created_at` value is a string like `2026-03-14T15:00:00Z` that can be parsed with a standard datetime library.
**Actual outcome:** The value was `1741964400` — a Unix timestamp integer. The datetime parser raised a type coercion failure. The data contract documentation describes the field as a "timestamp" without specifying the format, and the producing service serializes it as epoch seconds while the consuming code assumed ISO 8601.
**Interpretation:** I read "timestamp" as implying an ISO 8601 string because that is the dominant convention in the rest of this codebase. The schema documentation does not specify the serialization format, so the producer and consumer made different format assumptions. The result did not match the caller's expected format but the run continued with degraded date display.
---
```

### Entry 8: Code returns collection when caller expects single value

```markdown
## Entry 8: Code returns collection when caller expects single value
**Recorded:** 2026-03-14 15:42:19 UTC
**Category:** code/output-mismatch/blocked
**Tags:** code,output-mismatch,blocked
**Instruction source:** `src/resolver.py:84` (function docstring)
**Instruction text:** "Returns the resolved config entry for the given key."
**Action taken:** Called `resolve_config("database.host")` and used the return value as a string in a connection-string template.
**Expected outcome:** A single config value (string) for the `database.host` key, as the docstring says "the resolved config entry" (singular).
**Actual outcome:** The function returned a list of two values `["db-primary.internal", "db-replica.internal"]` because the key matched multiple config sources. The connection template rendered `['db-primary.internal', 'db-replica.internal']` as a literal string. The code ran without error but the downstream connection attempt failed quietly. The result did not match the caller's expected single-value return.
**Interpretation:** I read "the resolved config entry" as promising one value. The function returns all matches as a list without the docstring mentioning this. The runtime behavior diverged from what the docstring described.
---
```

### Entry 9: Inverted exit-code check in retry policy

```markdown
## Entry 9: Inverted exit-code check in retry policy
**Recorded:** 2026-03-14 15:50:33 UTC
**Category:** logic/output-mismatch/noisy
**Tags:** logic,output-mismatch,noisy
**Instruction source:** `lib/retrier.py:30` (retry loop logic)
**Instruction text:** "Retry the operation up to 3 times on failure. The algorithm checks the exit status and retries if the result indicates a transient error."
**Action taken:** Invoked the retry wrapper around a deployment health check.
**Expected outcome:** The wrapper retries on non-zero exit statuses (failures) and stops on status 0 (success).
**Actual outcome:** The wrapper retried on exit 0 (success) and stopped on exit 1 (failure). The health check succeeded on the first try but the algorithm re-ran it twice more, then accepted a subsequent failure as the final result. The retry behavior did not match the documented semantics — the assumption about what exit code 0 means was inverted.
**Interpretation:** The retry logic treats status 0 as the retry-worthy condition and non-zero as success. This is the inverse of standard success/failure semantics. The algorithm's structure is correct — it checks, branches, and counts properly — but the foundational assumption about exit-status meaning was wrong, so the correct behavior looked like failure to the wrapper.
---
```

### Entry 10: Flaky test suite in build script

```markdown
## Entry 10: Flaky test suite in build script
**Recorded:** 2026-03-14 15:58:07 UTC
**Category:** script/nondeterminism/noisy
**Tags:** script,nondeterminism,noisy,posix-sh
**Instruction source:** `scripts/build.sh:44`
**Instruction text:** "Run the full test suite as part of the build. If tests fail, the build is considered broken."
**Action taken:** Ran `sh scripts/build.sh` which internally invokes `pytest tests/`.
**Expected outcome:** A deterministic pass/fail result indicating whether the code change is correct.
**Actual outcome:** The test suite reported 2 test errors in `tests/test_api.py` on the first run. On retry with no code change, all tests passed. On a third run, 1 of the 2 tests errored again. The test is flaky — the pass/fail result sometimes depends on execution timing rather than code correctness.
**Interpretation:** I had no way to distinguish whether my code change caused the errors or the test is nondeterministic. The repeated retries wasted effort without yielding new signal about the code change. The build output does not separate deterministic errors from flaky ones.
---
```

### Entry 11: Orchestrator handoff loses file list context

```markdown
## Entry 11: Orchestrator handoff loses file list context
**Recorded:** 2026-03-14 16:05:22 UTC
**Category:** workflow/context-loss/degraded
**Tags:** workflow,context-loss,degraded,context,handoff
**Instruction source:** Orchestrator handoff message
**Instruction text:** "Continue the review of the remaining files. Focus on correctness and style."
**Action taken:** Received the delegation and began reviewing. Since no file list was provided in the handoff, I ran a full repository scan to identify review candidates.
**Expected outcome:** The handoff would include the list of files still pending review so the subagent could pick up where the orchestrator left off.
**Actual outcome:** The handoff said "remaining files" but did not pass the list. I re-scanned the entire repository and reviewed 14 files, including 9 that the orchestrator had already reviewed. The duplicated work was only discovered when the results were merged. The handoff forgot to include which files were already done.
**Interpretation:** The orchestrator delegated with a reference to "remaining files" without materializing the list. I had no way to know which files were already reviewed, so I started from scratch. The handoff forgot to carry over details that the orchestrator had but the subagent needed.
---
```

### Entry 12: Rate limit categorized as external-service/other

```markdown
## Entry 12: Rate limit misidentified as auth failure
**Recorded:** 2026-03-14 16:12:45 UTC
**Category:** external-service/other/blocked
**Tags:** external-service,other,blocked,token,api,rate-limit
**Instruction source:** CI pipeline step `fetch-pr-status`
**Instruction text:** "Query the GitHub API for the PR merge status."
**Action taken:** Called `GET /repos/org/repo/pulls/142` with the configured token.
**Expected outcome:** A 200 response with the PR status object.
**Actual outcome:** HTTP 403 with body `{"message":"API rate limit exceeded","documentation_url":"..."}` and `X-RateLimit-Remaining: 0` header. The request was blocked by quota exhaustion, not an authentication or authorization failure.
**Interpretation:** The 403 status code would normally indicate an auth problem, but the response body and rate-limit headers confirm this is quota exhaustion. The token is valid — the same request succeeded minutes earlier. The service blocked progress due to rate limiting.
---
```

**Calibration note:** The auto-categorizer now treats rate-limit and quota signals such as `API rate limit exceeded`, `X-RateLimit-Remaining`, and `Retry-After` as `other` mode even when the response status is `403`. That keeps quota exhaustion distinct from true auth failures and preserves the intended `external-service/other/blocked` category without a manual override.

### Entry 13: Referenced runbook does not exist

```markdown
## Entry 13: Referenced runbook does not exist
**Recorded:** 2026-03-14 16:18:30 UTC
**Category:** instructions/missing/blocked
**Tags:** instructions,missing,blocked,agents-md
**Instruction source:** AGENTS.md:52
**Instruction text:** "Follow the deployment runbook at `docs/runbooks/deploy-staging.md` before pushing to staging."
**Action taken:** Searched for the referenced file with `find docs/runbooks/ -name 'deploy-staging.md'` and `grep -r 'deploy-staging' docs/`.
**Expected outcome:** The file exists at the stated location and contains deployment instructions.
**Actual outcome:** The file was not found. The `docs/runbooks/` directory exists but contains only `rollback.md` and `monitoring.md`. No file matching `deploy-staging` was found anywhere in the repository. The instruction references a runbook that does not exist.
**Interpretation:** I followed the explicit file reference in AGENTS.md. The instruction points to a specific file that is absent from the repository. I could not proceed with the deployment preparation because the referenced steps do not exist.
---
```

---

## Bad entries

### Bad entry 1: Jumps to a fix

```markdown
The dispatch role is wrong. It should be `architecture-critic`.
```

Why it is bad:

- it does not say what the agent read
- it does not say what the agent tried
- it does not say what happened
- it turns the log into a patch suggestion

### Bad entry 2: Vague logging with no diagnostic value

```markdown
## Entry 4: MCP tool issue
**Recorded:** 2026-03-14 15:30:00 UTC
**Category:** mcp/other/degraded
**Instruction source:** MCP server
**Action taken:** Called the tool.
**Actual outcome:** It did not work. Tried again and it worked.
**Interpretation:** Something was wrong with the MCP tool temporarily.
---
```

Why it is bad:

- "MCP server" is not a specific instruction source — which server? which tool?
- "Called the tool" — which tool? with what arguments?
- "It did not work" — what error? what response? what status code?
- "Tried again and it worked" — was there a wait? a parameter change? same exact call?
- "Something was wrong temporarily" — this is not an interpretation, it is a restatement of the outcome
- a reader cannot trace the chain, reproduce the issue, or determine the category

### Bad entry 3: Editorializing instead of diagnosing

```markdown
## Entry 5: Terrible auth flow design
**Recorded:** 2026-03-14 16:00:00 UTC
**Category:** external-service/auth/blocked
**Instruction source:** API documentation
**Action taken:** Tried to authenticate with the service.
**Actual outcome:** The auth flow is overly complicated and should use OAuth2 instead of API keys. The API design is bad and the documentation is terrible. No modern service should require manual key rotation.
**Interpretation:** This is a terrible API design choice that wastes developer time.
---
```

Why it is bad:

- "terrible", "bad", "should use OAuth2" — quality judgments do not belong in a diagnostic log
- the actual outcome describes opinions, not what happened (no error message, no status code)
- the interpretation is an editorial, not a reasoning chain
- it does not record what the agent read, what it expected, or what went wrong
- a reviewer cannot distinguish between an auth failure and a design disagreement

---

## INDEX.md example

What a real `INDEX.md` looks like after 2 agents log entries across 2 log files in the same task directory. This example is illustrative — actual INDEX.md files are generated by `build-index.sh`.

```markdown
# Friction Index: abc-1234

**Generated:** 2026-03-14 16:30:00 UTC
**Task dir:** /tmp/agent-friction/abc-1234
**Task summary:** Investigate MCP routing failures
**Log files:** 2
**Entries:** 3

## Category counts

- `mcp/output-mismatch/degraded` - 1
- `instructions/missing/blocked` - 1
- `script/crash/blocked` - 1

## Log files

- `2026-03-14/16-00-00_orchestrator.md` - 2 entries
- `2026-03-14/16-10-00_subagent.md` - 1 entries
```

Notes:

- Category counts merge identical categories across all log files in the task directory
- The log file listing shows entry counts per file
- `INDEX.md` is the summary layer — it does not duplicate entry content
