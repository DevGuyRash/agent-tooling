# Output Contract

Required IDs:
- `AC-*` acceptance criteria
- `IMG-*` image profiles
- `RSK-*` risk/unknown entries
- `O-*` order contract tokens

Required major sections:
1. Requirements
2. Mode Applicability Matrix
3. Image Research
4. Unknown Unknowns
5. Build Overview
6. Build Design Plan
7. Visualization
8. Task List
9. Project Layout/Prerequisites
10. Generated Files
11. Operational Guide

Generated files must include inline traceability comments at the exact lines implementing key decisions.
Major sections must use H1 headings (`# Section Name`); lower heading levels are ignored by contract validation.
Policy artifacts (`policy-check` and `policy-plan`) must be machine-readable and deterministic.
Validate with: `./scripts/docker-architect-image output-check <output.md> --mode image`.
