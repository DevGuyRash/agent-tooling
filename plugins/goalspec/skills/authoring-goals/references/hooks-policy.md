# Hook Policy

Hooks are guardrails, not a substitute for good contracts.

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

Block dangerous commands and explicit out-of-scope paths when detected. Because hook interception is not complete, audit hash and report evidence at close.

## PostToolUse: evidence capture

Save tool-use events to `.goals/evidence/events/` when an active contract exists. Surface evidence paths as additional context.

## UserPromptSubmit: goal launch guard

If a user prompt starts `/goal` but does not reference `.goals/current.md` or `$authoring-goals`, add context warning that long-running work should be compiled first.

## Stop: final evidence gate

If the last assistant message appears to claim completion but omits required report fields, continue with a prompt asking for missing evidence. An achievement claim must reference the verifier pass/fail result (the oracle), not merely that files changed — evidence presence is not verification success. If the contract hash changed, continue and require the agent to report the contract mutation as failure.

The Stop hook is defense-in-depth, not the oracle. The authoritative close decision is `audit_goal.py` reading the `goalspec.verifier.v1` result file: `achieved` requires a passing verifier result plus required report sections plus a matching contract hash. A missing result for an executable verifier is inconclusive, and a failing result is not achieved.
