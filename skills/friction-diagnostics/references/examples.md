# Examples

## Good entries

### Event 1: Dispatch role slug mismatch

```markdown
## Event 1: Dispatch role slug mismatch
**Recorded:** 2026-03-14 15:02:11 UTC
**Derived category:** skill/name-resolution/blocked
**Guidance quality:** clear
**Tags:** skill,name-resolution,blocked,clear,dispatch,role,slug
**Instruction source:** SKILL.md:160, inside the "Domain routing" table
**Instruction text:** "Use `mpcr protocol dispatch --role <ROLE>` to get the domain-specific prompt." The table directly above this line lists domains with labels: "Architecture", "Security", "Performance". No column distinguishes display labels from CLI slugs.
**Action taken:** Ran `mpcr protocol dispatch --role architecture`. I picked the label "Architecture" from the table, lowercased it, and passed it as the `<ROLE>` value.
**Expected outcome:** The CLI prints the architecture domain prompt to stdout. The instruction says `--role <ROLE>` with no further qualification, and the table shows "Architecture" as a domain, so I expected the label to be the slug.
**Actual outcome:** `error: unknown dispatch role: architecture` — exit code 1. The CLI does not list valid slugs in its error output or `--help`.
**Interpretation:** I understood `<ROLE>` to mean the domain labels shown in the table immediately above the instruction, because nothing in SKILL.md distinguishes the visible label from the internal slug. The phrasing "Use ... --role <ROLE>" directly follows the table, which made the labels look like the intended values. I lowercased "Architecture" because CLI slugs are conventionally lowercase.
---
```

Why it is good:

- interpretation explains what language the agent read and why it was reasonable to read it that way
- it describes the specific table context that led to the assumption
- it includes the exact command, the reasoning behind the argument choice, and the full error
- it does not diagnose the root cause or suggest what the slug should be

### Event 2: MCP search tool overpromises readable content

```markdown
## Event 2: MCP search tool overpromises readable content
**Recorded:** 2026-03-14 15:04:33 UTC
**Derived category:** mcp/output-mismatch/degraded
**Guidance quality:** clear
**Tags:** mcp,output-mismatch,degraded,clear,output
**Instruction source:** MCP tool description for `gmail_search`, field: description
**Instruction text:** "The tool description says: 'Search and read emails matching a query. Returns matching messages with their content.' The parameter schema lists one required field: `query` (string)."
**Action taken:** Called `gmail_search` with `{"query": "from:boss@company.com subject:quarterly review"}`. The task required summarizing email content, so I expected this single call to return message bodies based on the description's "read emails" and "their content" language.
**Expected outcome:** An array of message objects each containing at minimum: subject, from, date, and a body or content field with the readable message text. The description says "read emails" and "their content", which I took to mean the search result itself includes readable bodies.
**Actual outcome:** Received 12 result objects. Each contained only: `id`, `threadId`, `subject`, `from`, `date`, and a `snippet` field with roughly 40 characters of truncated plaintext. No `body`, `content`, `text`, or `html` field. The response shape has no field that could contain the full message. I would need to call a separate `gmail_get_message` per result ID to retrieve bodies, but neither the tool description nor the parameter schema mentioned this two-step pattern.
**Interpretation:** I understood "search and read emails" and "returns matching messages with their content" to mean the search operation itself delivers readable message bodies in one call. The word "read" in the description and "their content" in the return description both pointed toward body text being included. I did not expect a metadata-only search that requires a second per-message call, because the description does not mention or link to a separate retrieval tool.
---
```

Why it is good:

- interpretation explains which specific words ("read", "their content") drove the agent's understanding
- it includes the exact tool call parameters and the full response shape
- it explains what the agent would have needed to know (the two-step pattern) without suggesting the tool should change
- the reasoning chain is traceable: specific language → specific assumption → specific mismatch

### Event 3: Ambiguous acceptance criteria in AGENTS.md

```markdown
## Event 3: Ambiguous acceptance criteria in AGENTS.md
**Recorded:** 2026-03-14 15:09:02 UTC
**Derived category:** instructions/ambiguity/continued
**Guidance quality:** ambiguous
**Tags:** instructions,ambiguity,continued,ambiguous,agents-md
**Instruction source:** AGENTS.md:34, under the "## PR standards" heading
**Instruction text:** "Keep the change minimal and production ready. The migration is optional if the feature works without it." These two sentences appear consecutively with no further elaboration. The surrounding section does not define "production ready" or give examples of what "optional" means in this context.
**Action taken:** Prepared a minimal patch that implements the feature without the migration. I deferred the migration entirely because the instruction explicitly calls it "optional" and I was prioritizing the "minimal" constraint. I did not add a note to the PR explaining the deferral because the instruction seemed clear enough.
**Expected outcome:** The reviewer accepts the patch without the migration, consistent with the instruction calling it optional. "Keep the change minimal" and "optional" both point toward a smaller scope.
**Actual outcome:** The reviewer commented: "Why wasn't the migration included? This feature isn't production ready without it." The reviewer read "production ready" as the dominant constraint and treated the migration as required for production readiness despite the "optional" qualifier. The PR was sent back for revision.
**Interpretation:** I understood the two sentences as having a priority order: "minimal" first, then "production ready" as a quality bar on the minimal change, with the migration carved out by "optional". The word "optional" in my reading was a direct exemption. I did not consider that "production ready" might override the "optional" qualifier because the instruction presents them as coordinated guidance, not as competing constraints. The phrase "if the feature works without it" seemed to settle the question — the feature does work without the migration.
---
```

Why it is good:

- interpretation explains the agent's reading of specific language: "minimal" as priority, "optional" as exemption, "if the feature works" as the settled condition
- it records both sides (agent's reading vs reviewer's reading) without declaring either correct
- it includes the surrounding context (what section it was in, what was absent from the guidance)
- the action taken explains the full decision, including what the agent chose NOT to do

### Event 4: Script crash from shell incompatibility

```markdown
## Event 4: Script crash from shell incompatibility
**Recorded:** 2026-03-14 15:15:41 UTC
**Derived category:** script/crash/blocked
**Guidance quality:** clear
**Tags:** script,crash,blocked,clear,posix-sh
**Instruction source:** README.md:22, under "## Verification"
**Instruction text:** "Run `scripts/verify.sh` to validate the build output." The README does not specify which shell to use. The script's first line is `#!/bin/sh`. No mention of bash anywhere in README.md or the script's comments.
**Action taken:** Ran `sh scripts/verify.sh` in the project container (Ubuntu 24.04 slim image). I used `sh` because the shebang says `#!/bin/sh` and the README says to run the script without specifying bash. Checked `ls -la /bin/sh` before running — it symlinks to `/usr/bin/dash`.
**Expected outcome:** The script validates build output and prints a pass/fail summary. The shebang and README both imply `sh` compatibility.
**Actual outcome:** Immediate crash on line 14: `scripts/verify.sh: 14: scripts/verify.sh: Syntax error: "(" unexpected` — exit code 2. Line 14 contains `local files=()`, which is bash array initialization syntax. dash does not support arrays or the `local var=()` form. The script never ran a single validation step.
**Interpretation:** I understood `#!/bin/sh` to mean the script is written for POSIX sh, because that is the universal convention for that shebang. The README's `scripts/verify.sh` invocation reinforced this — no `bash` prefix, no bash caveat. I had no reason to suspect bash-specific syntax behind a `#!/bin/sh` shebang. The instruction source (README.md) and the script's own shebang both told me `sh` is the correct interpreter.
---
```

### Event 5: Missing dependency in container environment

```markdown
## Event 5: Missing dependency in container environment
**Recorded:** 2026-03-14 15:20:58 UTC
**Derived category:** environment/missing/blocked
**Guidance quality:** clear
**Tags:** environment,missing,blocked,clear,dependency
**Instruction source:** Dockerfile:47, inline comment above a `RUN` directive
**Instruction text:** "# Run the scanning step: `uv run scan.py`". This appears as a comment inside the Dockerfile's build stage, directly above `RUN uv run scan.py`. The Dockerfile's package installation block (lines 8-22) installs `python3.12`, `python3-pip`, and `curl`, but does not mention `uv`. No `requirements.txt` or `pyproject.toml` references uv either.
**Action taken:** Ran `uv run scan.py` inside the running container (Ubuntu 24.04 slim, Python 3.12). I used the exact command from the Dockerfile comment. Before running, I confirmed Python was available via `python3 --version` (3.12.3) but did not check for `uv` specifically because the Dockerfile implied the image was self-contained.
**Expected outcome:** The scan runs and produces output. The Dockerfile itself contains the `uv run` directive, which implies the image has uv installed — otherwise the Dockerfile's own build would fail at that layer.
**Actual outcome:** `sh: uv: command not found` — exit code 127. `which uv` returned nothing. `pip list` did not include uv. The Dockerfile's build stage apparently succeeds because it runs in a different base image or build context that has uv, but the runtime image does not carry it over.
**Interpretation:** I understood the Dockerfile comment as an instruction to run the scan in the container, and I assumed the runtime image would have the same tools as the build stage because the Dockerfile does not use an explicit multi-stage pattern with different bases. The comment says "run the scanning step" as a directive, not as a build-only note. Nothing in the Dockerfile or its comments distinguishes build-time tools from runtime-available tools.
---
```

### Event 6: CLI flag contradicts actual behavior

```markdown
## Event 6: CLI flag contradicts actual behavior
**Recorded:** 2026-03-14 15:28:14 UTC
**Derived category:** tool/contradiction/blocked
**Guidance quality:** misleading
**Tags:** tool,contradiction,blocked,misleading,cli,output
**Instruction source:** `lint-runner --help` output, under the `--format` flag section
**Instruction text:** "The `--help` output reads: '--format <FORMAT>  Output format: text, html, sarif (default: text)'. The word 'html' appears in the enumeration of valid values alongside 'text' and 'sarif', separated by commas, presented as parallel choices."
**Action taken:** Ran `lint-runner --format html src/` to produce browser-viewable lint results. I chose `html` directly from the `--help` enumeration because the task asked for a shareable report and HTML was listed as supported.
**Expected outcome:** Lint results printed as HTML to stdout or a file, consistent with `--help` listing `html` as one of three accepted format values.
**Actual outcome:** `error: invalid value 'html' for '--format': valid values are text, sarif` — exit code 1. The error's own "valid values" list does not include `html`, directly contradicting the `--help` text. Running `lint-runner --format text src/` succeeded immediately afterward, confirming the tool works and only the `html` option is broken or removed.
**Interpretation:** I understood `--help` as the authoritative list of accepted values. The `html` option is presented identically to `text` and `sarif` — same position, same comma-separated format, no deprecation note, no asterisk. There was no version note, changelog, or flag annotation that would have warned me `html` was no longer accepted. I took the help text at face value because that is the standard way to discover a CLI's accepted inputs.
---
```

**Calibration note:** With the current wording, the auto-categorizer already lands on `tool/contradiction/blocked`. If you wanted to emphasize steerability rather than hard failure for a similar case, the only plausible override would be the `run_effect` axis.

### Event 7: Data contract uses wrong timestamp format

```markdown
## Event 7: Data contract uses wrong timestamp format
**Recorded:** 2026-03-14 15:35:47 UTC
**Derived category:** data/schema/degraded
**Guidance quality:** ambiguous
**Tags:** data,schema,degraded,ambiguous
**Instruction source:** `docs/data-contracts.md:18`, under "## EventRecord schema"
**Instruction text:** "All event records use the shared `EventRecord` structure. The `created_at` field contains the creation timestamp." The doc does not specify the format (ISO 8601, epoch seconds, or other). The field type is listed as "timestamp" with no further annotation. I also checked `src/models/event.py:12` where the field is declared as `created_at: int`, but I read the data-contract doc first and the model file did not surface during the initial task.
**Action taken:** Parsed the `created_at` value from a serialized event record using `datetime.fromisoformat(record['created_at'])`, treating it as an ISO 8601 string. I wrote the display formatter before examining a live payload because the data-contract doc implied a standard timestamp type.
**Expected outcome:** The `created_at` value is a string like `2026-03-14T15:00:00Z` that parses cleanly with a standard datetime library. Every other timestamp field in this codebase (`updated_at`, `deleted_at`, `started_at`) uses ISO 8601 strings, which is why I defaulted to that format.
**Actual outcome:** The value was `1741964400` — a bare integer. `datetime.fromisoformat('1741964400')` raised `ValueError: Invalid isoformat string`. Falling back to `datetime.fromtimestamp(int(record['created_at']))` produced the correct date. The display formatter rendered a fallback "(invalid date)" string in the UI until I patched the parser.
**Interpretation:** I understood "timestamp" to mean an ISO 8601 string because that is the format used by every other timestamp field in this codebase's data contracts, models, and API responses. The data-contract doc uses the word "timestamp" without qualification, which in the context of a codebase that defaults to ISO 8601 everywhere else, pointed me toward string parsing. The doc does not say "epoch seconds", "integer", or "Unix time". The `int` type annotation in the model file would have been a strong hint, but the data-contract doc was my entry point and it did not cross-reference the model.
---
```

### Event 8: Code returns collection when caller expects single value

```markdown
## Event 8: Code returns collection when caller expects single value
**Recorded:** 2026-03-14 15:42:19 UTC
**Derived category:** code/output-mismatch/blocked
**Guidance quality:** misleading
**Tags:** code,output-mismatch,blocked,misleading
**Instruction source:** `src/resolver.py:84`, function `resolve_config` docstring
**Instruction text:** "Returns the resolved config entry for the given key." The docstring uses the singular "entry" and the function name uses singular "config". The function signature is `def resolve_config(key: str) -> Any:` — the return type is `Any`, which does not hint at a collection. No examples or caveats in the docstring.
**Action taken:** Called `resolve_config("database.host")` and interpolated the return value directly into a connection-string template: `f"postgresql://{resolve_config('database.host')}:5432/app"`. I treated the return value as a string based on the singular docstring language and the fact that config values for host keys are conventionally single strings.
**Expected outcome:** A single config value (string) like `"db-primary.internal"` for the `database.host` key. The singular "the resolved config entry" and the function name both imply one result. The surrounding code in `src/db/connection.py` that calls this function also treats it as a scalar.
**Actual outcome:** The function returned `["db-primary.internal", "db-replica.internal"]` — a list of two values. The key matched entries in both `config/base.yaml` and `config/production.yaml`. The connection template rendered the list's repr: `postgresql://['db-primary.internal', 'db-replica.internal']:5432/app`. No error was raised. The downstream connection attempt failed silently because the URL was malformed. I discovered the issue 3 minutes later when the health check timed out.
**Interpretation:** I understood "the resolved config entry" (singular, with the definite article "the") to mean the function returns exactly one value after resolving across config sources. The word "resolved" reinforced this — resolution implies collapsing multiple sources to a single answer. The `-> Any` return type was not informative enough to warn me, and the docstring does not mention the possibility of a list return. I had no reason to wrap the call in a list check because the contract as written promises a scalar.
---
```

### Event 9: Inverted exit-code check in retry policy

```markdown
## Event 9: Inverted exit-code check in retry policy
**Recorded:** 2026-03-14 15:50:33 UTC
**Derived category:** logic/output-mismatch/noisy
**Guidance quality:** clear
**Tags:** logic,output-mismatch,noisy,clear
**Instruction source:** `lib/retrier.py:30`, the `retry_on_failure` function docstring and implementation
**Instruction text:** "Retry the operation up to 3 times on failure. The algorithm checks the exit status and retries if the result indicates a transient error." The function signature is `def retry_on_failure(cmd, max_retries=3)`. Line 34 contains the branch: `if result.returncode == 0: continue` — which re-enters the retry loop on success.
**Action taken:** Invoked `retry_on_failure(["./scripts/health-check.sh"])` to wrap a deployment health check that returns exit 0 on healthy and exit 1 on unhealthy. I used the wrapper as documented without modifying its internals because the docstring says it retries on failure.
**Expected outcome:** The wrapper runs the health check once, sees exit 0 (healthy), and returns immediately. If the check fails (exit 1), it retries up to 3 times. This is standard retry-on-failure semantics that matches the docstring's "retries if the result indicates a transient error".
**Actual outcome:** The health check succeeded on the first run (exit 0), but the wrapper re-ran it. On the second run it also succeeded (exit 0), and the wrapper re-ran it again. On the third run the health check returned exit 1 (a transient network blip). The wrapper accepted exit 1 as the final result and returned a failure status. Total: 3 unnecessary runs, with the final (wrong) result accepted. The deployment was marked unhealthy despite 2 of 3 runs succeeding.
**Interpretation:** I understood "retries on failure" and "retries if the result indicates a transient error" to mean the function retries when the exit code is non-zero, because exit 0 universally means success in POSIX conventions and the docstring uses the word "failure". The `retry_on_failure` function name itself says "on failure". I did not read the implementation before calling it because the docstring was unambiguous. The `if result.returncode == 0: continue` on line 34 is the opposite of what the docstring describes — it retries on success — but this only becomes visible by reading the code, not the documentation.
---
```

### Event 10: Flaky test suite in build script

```markdown
## Event 10: Flaky test suite in build script
**Recorded:** 2026-03-14 15:58:07 UTC
**Derived category:** script/nondeterminism/noisy
**Guidance quality:** clear
**Tags:** script,nondeterminism,noisy,clear,posix-sh
**Instruction source:** `scripts/build.sh:44`, inside the `run_tests()` function
**Instruction text:** "Run the full test suite as part of the build. If tests fail, the build is considered broken." The script calls `pytest tests/ --tb=short` and exits with pytest's return code. There is no `--count`, `--reruns`, or flaky-test annotation.
**Action taken:** Ran `sh scripts/build.sh` three times, each time with no code changes between runs. The first run was to verify my change. The second and third runs were to investigate the failure. I did not add `-x` or `--lf` flags because the build script does not accept passthrough arguments.
**Expected outcome:** A deterministic pass/fail result: the same code produces the same test result. The instruction says "if tests fail, the build is considered broken", which I understood to mean test results are reliable indicators of code correctness.
**Actual outcome:** Run 1: `FAILED tests/test_api.py::test_rate_limit_header` and `tests/test_api.py::test_concurrent_connections` — 2 failures, exit code 1. Run 2 (no changes): all 47 tests passed, exit code 0. Run 3 (no changes): `FAILED tests/test_api.py::test_rate_limit_header` — 1 failure, exit code 1. The two failing tests both involve timing-sensitive assertions on HTTP response headers.
**Interpretation:** I understood "if tests fail, the build is considered broken" to mean test results are a reliable signal about my change. After the first failure, I assumed my code change broke something. The second run passing with zero changes was the first indication that the test itself might be nondeterministic. I ran a third time to confirm. The build script gives no way to distinguish timing-sensitive tests from deterministic ones, and the instruction treats all test failures equally as "broken", so I had no basis to ignore the failures and had to spend time ruling out my change as the cause.
---
```

### Event 11: Orchestrator handoff loses file list context

```markdown
## Event 11: Orchestrator handoff loses file list context
**Recorded:** 2026-03-14 16:05:22 UTC
**Derived category:** workflow/context-loss/degraded
**Guidance quality:** clear
**Tags:** workflow,context-loss,degraded,clear,context,handoff
**Instruction source:** Orchestrator handoff message, delivered via the task delegation payload
**Instruction text:** "Continue the review of the remaining files. Focus on correctness and style." The handoff included the repository path and branch name but no file list, no diff summary, and no mention of which files the orchestrator had already reviewed. The orchestrator's own context had reviewed `src/auth.py`, `src/middleware.py`, `src/routes/api.py`, `src/routes/health.py`, and 5 test files.
**Action taken:** Received the delegation and looked for a file list in the handoff payload, SESSION.txt, and the task directory. Found none. Ran `find src/ tests/ -name '*.py' -newer .git/refs/heads/main` to identify review candidates, which returned 14 files. Began reviewing all 14 because I had no way to exclude the ones the orchestrator had already covered.
**Expected outcome:** The handoff would include a manifest of files still pending review — either as a list in the delegation message, or as a pointer to a file in the task directory. The phrase "remaining files" implies a defined set that the sender knows and the receiver can act on.
**Actual outcome:** Reviewed all 14 files, producing review comments for each. When the orchestrator merged results, 9 of the 14 files had duplicate reviews. The orchestrator's and my comments occasionally contradicted each other on style points. The merged output required manual deduplication. Total wasted effort: approximately 20 minutes of redundant review on the 9 already-covered files.
**Interpretation:** I understood "remaining files" to mean the orchestrator had a specific set in mind and would pass it along, because the word "remaining" implies subtraction from a known total. When no list appeared in the handoff, I had two choices: ask for clarification (which the delegation protocol does not support for subagents in this workflow) or scan from scratch. I chose to scan from scratch because the instruction said "continue" which implied urgency. I did not assume the orchestrator had reviewed any particular files because the handoff gave me no basis for that assumption.
---
```

### Event 12: Rate limit categorized as external-service/other

```markdown
## Event 12: Rate limit misidentified as auth failure
**Recorded:** 2026-03-14 16:12:45 UTC
**Derived category:** external-service/other/blocked
**Guidance quality:** clear
**Tags:** external-service,other,blocked,clear,token,api,rate-limit
**Instruction source:** CI pipeline step `fetch-pr-status`, configured in `.github/workflows/ci.yaml:87`
**Instruction text:** "Query the GitHub API for the PR merge status." The pipeline step uses `curl -H "Authorization: Bearer $GITHUB_TOKEN"` with the repository's default `GITHUB_TOKEN`. No rate-limit handling, retry logic, or fallback is configured in the step.
**Action taken:** Called `GET /repos/org/repo/pulls/142` with the configured token. This was the 4th API call in the pipeline within a 60-second window — the previous 3 calls (check status, list reviews, list checks) all succeeded with 200 responses. I did not add rate-limit awareness because the pipeline step does not mention it and 4 calls seemed well within normal limits.
**Expected outcome:** A 200 response with the PR status object containing `state`, `merged`, and `mergeable` fields. The same call succeeded 2 minutes earlier during a manual test.
**Actual outcome:** HTTP 403 with body `{"message":"API rate limit exceeded","documentation_url":"https://docs.github.com/rest/overview/rate-limiting"}` and headers `X-RateLimit-Remaining: 0`, `X-RateLimit-Reset: 1741965600`. The response status 403 initially looked like an auth or permissions failure, but the body and headers are GitHub's standard rate-limit response, not an auth rejection.
**Interpretation:** I understood the CI step as a straightforward API query with a valid token. The 403 status code initially suggested the token lacked permissions — my first reaction was to check the token's scopes. But the response body explicitly says "rate limit exceeded" and the `X-RateLimit-Remaining: 0` header confirms quota exhaustion. The token is valid (it worked seconds before). I initially categorized this as `auth` because of the 403, but the body evidence overrides the status code. The pipeline step gives no guidance about rate limits and does not retry or back off.
---
```

**Calibration note:** The auto-categorizer now treats rate-limit and quota signals such as `API rate limit exceeded`, `X-RateLimit-Remaining`, and `Retry-After` as `other` mode even when the response status is `403`. That keeps quota exhaustion distinct from true auth failures and preserves the intended `external-service/other/blocked` category without a manual override.

### Event 13: Referenced runbook does not exist

```markdown
## Event 13: Referenced runbook does not exist
**Recorded:** 2026-03-14 16:18:30 UTC
**Derived category:** instructions/missing/blocked
**Guidance quality:** clear
**Tags:** instructions,missing,blocked,clear,agents-md
**Instruction source:** AGENTS.md:52, under "## Deployment procedure"
**Instruction text:** "Follow the deployment runbook at `docs/runbooks/deploy-staging.md` before pushing to staging." The path is formatted as an inline code reference, presented as a concrete file location, not a placeholder or example. The surrounding paragraph treats the runbook as a prerequisite: "Before pushing to staging, you must complete all steps in the runbook."
**Action taken:** Ran `find docs/runbooks/ -name 'deploy-staging.md'` — no results. Ran `grep -r 'deploy-staging' docs/` — no results. Ran `ls docs/runbooks/` — found `rollback.md` and `monitoring.md` only. Checked `git log --all --diff-filter=D -- docs/runbooks/deploy-staging.md` to see if the file was deleted — no history of it ever existing on any branch. Also searched for alternate names: `deploy.md`, `staging.md`, `deploy-staging.yaml` — none found.
**Expected outcome:** The file `docs/runbooks/deploy-staging.md` exists at the stated path and contains a step-by-step deployment procedure. AGENTS.md gives the path as an inline code reference in a sentence that says "follow the runbook", implying it is a real, current file.
**Actual outcome:** The file does not exist and has never existed in the repository's git history. The `docs/runbooks/` directory is real and contains other runbooks, which makes the reference look plausible — it is not a generic placeholder path. There are no alternative deployment docs anywhere in the repository. I cannot complete the deployment preparation because AGENTS.md says the runbook is a prerequisite and I have no way to obtain the referenced steps.
**Interpretation:** I understood `docs/runbooks/deploy-staging.md` as a literal path to an existing file because AGENTS.md presents it in code formatting within a concrete instruction ("Follow the deployment runbook at ..."). The instruction does not say "create" or "see template" — it says "follow", which implies the file is already there with steps to execute. The existence of other runbooks in the same directory reinforced the expectation that this one should also be present.
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
## Event 4: MCP tool issue
**Recorded:** 2026-03-14 15:30:00 UTC
**Derived category:** mcp/other/degraded
**Instruction source:** MCP server
**Action taken:** Called the tool.
**Actual outcome:** It did not work. Tried again and it worked.
**Interpretation:** Something was wrong with the MCP tool temporarily.
---
```

Why it is bad:

- "MCP server" is not a specific instruction source — which server? which tool? which parameter?
- "Called the tool" — which tool? with what arguments? what did the request look like?
- "It did not work" — what error? what response? what status code? what fields were present or absent?
- "Tried again and it worked" — was there a wait? a parameter change? same exact call? how long between attempts?
- "Something was wrong temporarily" — this is not an interpretation, it is a vague diagnosis. An interpretation should say "I understood the tool description to mean X because it said Y, so I expected Z"
- a reader cannot trace the chain, reproduce the issue, or determine the category

### Bad entry 3: Editorializing instead of diagnosing

```markdown
## Event 5: Terrible auth flow design
**Recorded:** 2026-03-14 16:00:00 UTC
**Derived category:** external-service/auth/blocked
**Instruction source:** API documentation
**Action taken:** Tried to authenticate with the service.
**Actual outcome:** The auth flow is overly complicated and should use OAuth2 instead of API keys. The API design is bad and the documentation is terrible. No modern service should require manual key rotation.
**Interpretation:** This is a terrible API design choice that wastes developer time.
---
```

Why it is bad:

- "terrible", "bad", "should use OAuth2" — quality judgments do not belong in a diagnostic log
- the actual outcome describes opinions, not what happened (no error message, no status code, no response)
- the interpretation is an editorial opinion, not a witness statement about what the agent understood — it should say "I understood the docs to mean I should use an API key and followed the key generation steps, but the generated key was rejected with status 401 and I found no guidance on key format requirements"
- it does not record what the agent read, what specific text it followed, or what the auth flow actually required
- a reviewer cannot distinguish between an auth failure and a design disagreement

---

## INDEX.md example

What a real `INDEX.md` looks like after 2 agents log entries across 2 log files in the same task directory. This example is illustrative — actual INDEX.md files are generated by `build-index.sh`.

```markdown
# Friction Index: abc-1234

**Generated:** 2026-03-14 16:30:00 UTC
**Task dir:** /tmp/agent-friction/abc-1234
**Task summary:** Investigate MCP routing failures — inspect_build returns stale metadata and dispatch roles do not resolve against documented domain labels
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
