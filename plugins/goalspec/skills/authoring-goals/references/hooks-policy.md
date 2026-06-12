# Hook Policy

Hooks are guardrails, not a substitute for good contracts. They are
defense-in-depth, not an absolute boundary — the freeze backstop is
render-refuse-unlocked plus the audit hash, not the hooks.

## Codex runtime, trust, and conformance

- Hooks are **enabled by default** on Codex. Disable them with `[features] hooks = false`
  in config (`codex_hooks` is a deprecated alias; do not rely on it, and
  `codex_hooks = true` is not required).
- Plugin-bundled hooks require a **trust review** before they run: review and approve
  them with `/hooks`. The default path `hooks/hooks.json` needs no manifest field.
- Hook commands receive `PLUGIN_ROOT` / `PLUGIN_DATA` / `CLAUDE_PLUGIN_ROOT` /
  `CLAUDE_PLUGIN_DATA`; the wired commands use `"${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/hooks/scripts/..."`
  so they resolve on either host.
- **PreToolUse** intercepts Bash, `apply_patch` (matchers `apply_patch|Edit|Write`,
  canonical `tool_name: apply_patch`), and MCP calls — but not all shell calls.
  **PostToolUse** runs after Bash/`apply_patch`/MCP and **cannot undo** side effects.
- Because interception is incomplete and irreversible after the fact, the
  authoritative freeze is the audit hash (`audit_goal.py`) and render refusing to
  project an unlocked contract — not the hooks.
- **Observed live coverage (Codex 0.138.0, 2026-06-10, `approval_policy = never` +
  `danger-full-access`):** UserPromptSubmit, PostToolUse, and Stop fired;
  **PreToolUse never fired** despite using the same matcher as PostToolUse, so a
  direct append to the frozen contract executed undenied. On such runtimes the
  freeze is **detect-only**: the mutation is caught by the audit hash and the Stop
  gate, not prevented. Re-confirm per runtime with `conformance_probe.py observe`.
- **Observed live coverage (Codex, 2026-06-11, `permission_mode: bypassPermissions`,
  goalspec 1.2.0, real authoring run):** PostToolUse fired (29 captured events) and
  **PreToolUse fired and denied** protected-path commands live — the freeze
  *enforced* under full-access mode on this runtime, contradicting the 2026-06-10
  observation. Coverage varies by runtime and version: never assume either way;
  re-confirm per environment and keep the render-refuse + audit-hash backstop
  authoritative regardless.
- `conformance_probe.py` reports coverage on the installed runtime. `selftest`
  drives each wired hook with synthetic input and checks the documented decision
  shape offline; `observe`/`report` record and summarize what actually fired on a
  live session. If the runtime lags the docs, degrade gracefully and lean on the
  render-refuse-unlocked + audit-hash backstop, stating the observed coverage.
- **Upgrades break live sessions, loudly**: hook commands resolve the versioned
  plugin root at session start, and installers may prune the old version
  directory on upgrade. A hook error of the shape
  `can't open file '.../goalspec/<old-version>/hooks/scripts/...'` means a stale
  live session, not a broken install — restart the session; do not re-trust,
  reinstall, or weaken hooks to work around it. A failing UserPromptSubmit hook
  can block every prompt in that session until restart.

## PreToolUse: scope guard

Block obvious attempts to modify the frozen contract:

- `.goals/current.md`
- `.goals/current.sha256`
- `.goals/GOALS.md`
- `.goals/graph.json`
- `.goals/frontier.md`

Allow executor writes only under:

- `.goals/evidence/`
- `.goals/reports/`
- `.goals/rendered-*` (re-renderable projections; the pointer launch line's file
  hash makes tampering loud at launch, so write-prevention adds nothing here)

The guard exempts GoalSpec's own verification scripts (`validate_goal.py`,
`render_goal.py`, `audit_goal.py`, `run_verifiers.py`, `campaign_status.py`)
when they name protected paths read-only — the sanctioned close-out flow — but
still denies them when the command carries `--write-hash` (re-arming the lock
after a mutation) or `--write <protected-path>` (clobbering frozen state via
the renderer).

Matcher: `Bash|apply_patch|Edit|Write|mcp__.*` (MCP parity with PostToolUse). MCP
tool I/O is opaque, so there is no deterministic protected-path check for `mcp__*`
calls — they pass through, and the audit hash remains the backstop. Deny output uses
`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}`.
Block dangerous commands and explicit out-of-scope paths when detected. Because hook
interception is not complete, audit hash and report evidence at close.

## PostToolUse: evidence capture

Save tool-use events to `.goals/evidence/events/` when an active contract exists. Surface evidence paths as additional context.

### Evidence sensitivity

Capture is write-once (PostToolUse cannot undo side effects), so it sanitizes before writing. Common secret patterns (`Authorization: Bearer`, `*_API_KEY=`, `password=`, `token=`, `secret=`) are redacted to `[REDACTED]` and oversized strings are truncated (`GOALSPEC_EVIDENCE_MAX_BYTES`, default 16 KB). Redaction is best-effort and intentionally over-redacts — **evidence may still contain sensitive raw output**. `init_project.py` gitignores `.goals/evidence/` and `.goals/run_state.json` (runtime state lives at `.goals/evidence/run_state.json`); keep evidence local and do not paste it outside the project. `.goals/reports/` is the reviewable summary and stays tracked.

## UserPromptSubmit: goal launch guard

If a user prompt starts `/goal` but does not reference `.goals/current.md` or `$authoring-goals`, add context warning that long-running work should be compiled first. To block, emit `{"decision":"block","reason":"..."}` (or exit 2); a referenced-but-missing `.goals/current.md` is blocked.

## Render freeze gate

`render_goal.py` refuses to project an unlocked or hash-mismatched `current.md` into a `/goal` by default (exit 2). Lock first with `validate_goal.py .goals/current.md --write-hash`; pass `--allow-unlocked` only for a preview before locking. This refusal, with the audit hash, is the freeze backstop the hooks cannot fully guarantee.

## Stop: final evidence gate

If the last assistant message appears to claim completion but omits required report fields, continue with a prompt asking for missing evidence. An achievement claim must reference the verifier pass/fail result (the oracle), not merely that files changed — evidence presence is not verification success. A completion claim against an unlocked contract (no `current.sha256`) is blocked: it cannot be certified, so it must be locked or reported inconclusive/blocked. If the contract hash changed, continue and require the agent to report the contract mutation as failure.

Every block is **once per cause per contract**, tracked in `.goals/evidence/stop_guard_state.json` (and via `stop_hook_active` where the harness provides it). A mutated contract cannot be un-mutated by the executor, so re-blocking forever turns the anti-runaway gate into the runaway — observed live on Codex as 71 consecutive Stop blocks ended only by an external timeout. The marker fails open: when state cannot be read or written, the stop is allowed and the audit hash remains the authoritative gate.

Codex Stop I/O: allow/no-op is exit 0 with **no stdout**; continue the agent (block the stop) with `{"decision":"block","reason":"..."}` (or exit 2). A bare `{"continue": true}` is ambiguous on Codex, so allow paths stay silent — `conformance_probe.py` verifies this empirically.

The Stop hook is defense-in-depth, not the oracle. The authoritative close decision is `audit_goal.py` reading the `goalspec.verifier.v1` result file: `achieved` requires a passing verifier result plus required report sections plus a matching contract hash. A missing result for an executable verifier is inconclusive, and a failing result is not achieved.
