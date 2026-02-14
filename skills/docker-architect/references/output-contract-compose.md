# Output Contract

Required IDs:
- `AC-*` for acceptance criteria
- `IMG-*` for image research entries
- `RSK-*` for unknown-unknown/risk entries
- `O-*` for order contract references

Required major sections:
1. Requirements
2. Mode Applicability Matrix
3. Image Research
4. Unknown Unknowns
5. Deployment Overview
6. Architecture Plan
7. Visualization
8. Task List
9. Directory/Prerequisites
10. Configuration Files
11. Operational Guide

Always emit in order and only open the file-emission section after preconditions are satisfied.
Major sections must use H1 headings (`# Section Name`); lower heading levels are ignored by contract validation.
Policy artifacts (`policy-check` and `policy-plan`) must be machine-readable and deterministic.
Validate with: `./scripts/docker-architect-compose output-check <output.md> --mode compose`.
