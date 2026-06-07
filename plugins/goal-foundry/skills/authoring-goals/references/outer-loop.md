# Outer Loop Policy

Goal Foundry improves on persistent Ralph-style loops by splitting the system into two loops:

- Outer loop: open-world discovery and goal formation.
- Inner loop: closed-world execution of one frozen contract.

Default: the outer loop is human-stepped.

Lifecycle:

1. Inventory capabilities.
2. Scan requested context within an exploration budget.
3. Extract candidate goals with evidence.
4. Lint for launchability.
5. Select one ready goal, or report why none is launchable.
6. Compile `.goals/current.md`.
7. Validate and lock the contract hash.
8. Render the Codex `/goal` objective.
9. Run Codex `/goal` against the single contract.
10. Capture verifier evidence and final report.
11. Audit against `current.md` and hash lock.
12. Close status in `GOALS.md` and `graph.json`.
13. Stop. Do not launch the next goal without a new user instruction unless an explicit outer-loop budget exists.

Open-world done is not "there is no more work." It is "no additional launchable candidate was found within the stated frontier and budget."
