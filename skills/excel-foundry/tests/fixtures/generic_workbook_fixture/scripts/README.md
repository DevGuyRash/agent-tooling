# Legacy Fixture Scripts

This directory contains legacy fixture-only helper and regression scripts for a
local workbook fixture used in repo verification.

They are not part of the public `excel-foundry` skill contract and should
not be used as the documentation surface for the generic skill. The supported
and documented surfaces for the skill are:

- `<skills-file-root>/scripts/excel_workbook_sync.py`
- `<skills-file-root>/scripts/excel-foundry`
- the references under `<skills-file-root>/references/`

If you are working on the generic skill, use the documented workbook-agnostic
commands and protocols instead of the legacy fixture wrappers in this
directory.
