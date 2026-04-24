# Excel Foundry Development

Read this file only when modifying, testing, packaging, or reviewing the
Excel Foundry skill itself. Normal workbook tasks should use `SKILL.md` and the
task-specific reference files instead.

## Scope

Excel Foundry is an agent skill, not an application repo. Its committed files
should be portable instructions, scripts, fixtures, tests, and references that
work when copied to another host.

WHEN you change this skill's public behavior THEN you SHALL keep `SKILL.md`
focused on routing and progressive disclosure.

WHEN a detail is only useful to skill maintainers THEN you SHALL put it in this
file instead of `SKILL.md`.

WHEN a detail is useful only for a specific workflow THEN you SHALL put it in a
focused file under `references/` and link to it from `SKILL.md`.

## Privacy And Portability

You SHALL NOT commit user-specific, company-specific, customer-specific, or
machine-specific identifiers in tests, fixtures, scripts, docs, manifests, or
generated artifacts.

You SHALL treat workbook paths, usernames, company names, customer names,
business-unit names, source-system names, account/vendor/person identifiers,
asset identifiers, operational identifiers, request identifiers, payment identifiers, and workbook filenames from real user files
as sensitive unless they are already deliberately synthetic.

You SHALL NOT use hard-coded local paths such as `C:\Users\...`, shared-drive
paths, OneDrive/SharePoint paths, or repo-specific sibling paths in committed
files.

WHEN a test needs local real-world workbooks THEN you SHALL make it opt-in via
environment variables and keep the files under an ignored local directory such
as `.local/files/excel-foundry/`.

WHEN a fixture needs realistic labels THEN you SHALL use neutral synthetic
names such as `DATA_RECORDS`, `DATA_RECORD_LINES`, `tbl_records`,
`tbl_record_lines`, `Example Company`, `SAMPLE_CODE`, and `ASSET_NUMBER`.

WHEN a fixture needs realistic identifiers THEN you SHALL use obviously fake
values that cannot be confused with real people, companies, customers,
assets, operations, payments, vendors, or other real records.

WHEN downloading or collecting external workbook samples THEN you SHALL store
them outside git under `.local/`, record source URLs and hashes in local-only
indexes, and avoid adding workbook binaries to git history.

## Fixture Rules

Committed fixtures should prove generic workbook behavior, not encode a real
workflow from a specific employer, user, or system.

You SHALL NOT name fixture directories, files, worksheets, tables, Power Query
queries, VBA modules, functions, or tests after proprietary workflows or real
source systems.

WHEN adapting a real workbook-derived scenario into a committed fixture THEN
you SHALL sanitize names, paths, sample values, formulas, comments, query
source paths, macros, and documentation before committing.

WHEN a scenario is too specific to sanitize confidently THEN you SHALL keep it
in `.local/files/excel-foundry/` and run it only through opt-in external corpus
tests.

## Progressive Disclosure

`SKILL.md` should answer only:

- what the skill does
- when to use it
- which reference to load next
- which launcher/scripts exist
- how to run the baseline validation command

Reference files should hold workflow details. This file should hold maintainer
rules. Tests should encode behavioral guarantees.

## Pre-Commit Checks

Before considering Excel Foundry changes complete, run the relevant subset:

```powershell
python -m py_compile skills/excel-foundry/scripts/excel_workbook_sync.py skills/excel-foundry/scripts/excel_workbook_package.py
python -m unittest discover -s skills/excel-foundry/tests -p test_*.py
python <codex-home>/skills/.system/skill-creator/scripts/quick_validate.py skills/excel-foundry
```

Before committing, scan for sensitive identifiers:

```powershell
rg -n -i "<sensitive-patterns-for-this-skill>" skills/excel-foundry
```

WHEN this scan returns matches in committed Excel Foundry tests, scripts,
fixtures, or docs THEN you SHALL either remove the sensitive term or document
why it is a generic detector/configuration term rather than user data.

Before committing, verify workbook binaries are not tracked:

```powershell
git ls-files | Select-String -Pattern '\.(xlsx|xlsm|xlsb|xls)$'
git rev-list --objects --all | Select-String -Pattern '\.(xlsx|xlsm|xlsb|xls)$'
```

## Local Corpus

The preferred local corpus root is:

```text
.local/files/excel-foundry/
```

Local corpus contents are for validation only. They are not part of the skill
contract and should not appear in committed tests by exact filename, directory
name, source path, or workbook-specific count.

WHEN tests need the local corpus THEN they SHALL read a root from environment
variables such as `EXCEL_SYNC_EXTERNAL_ROOTS` and skip clearly when the corpus
is absent.


