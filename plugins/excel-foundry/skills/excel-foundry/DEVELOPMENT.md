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

WHEN writing production-facing instructions THEN you SHALL make them a
heuristic category router.

WHEN development procedure, fixture policy, or validation detail is needed
THEN you SHALL keep it in this file unless normal workbook execution needs a
one-line pointer.

You SHALL NOT add a production `README.md`; use `SKILL.md` for routing and
focused files under `references/` for details.

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

## Skill Metadata

The skill frontmatter is governed by the system skill validator.

You SHALL keep `SKILL.md` frontmatter limited to `name` and `description`.

You SHALL keep `name: excel-foundry`.

You SHALL NOT add `compatibility`, `metadata`, capability tables, or runtime
host details to `SKILL.md` YAML frontmatter.

WHEN runtime or host compatibility guidance changes THEN you SHALL update
`references/runtime-compatibility.md`, `references/excel-capability-matrix.json`,
or both instead of adding frontmatter fields.

## Capability Source Of Truth

`references/excel-capability-matrix.json` is the single source of truth for
what Excel Foundry can do, which backend owns it, whether it is supported,
partial, host-limited, preserve-only, or planned, and which tests prove that
claim.

You SHALL NOT create a second capability matrix, evidence ledger, checklist,
table, or roadmap that repeats surface support status outside
`references/excel-capability-matrix.json`.

WHEN planning a new Excel Foundry feature THEN you SHALL start by locating the
target surface in `references/excel-capability-matrix.json`.

WHEN the target surface does not exist in the matrix THEN you SHALL add it to
`references/excel-capability-matrix.json` before implementing public behavior.

WHEN a feature changes support status, route, backend ownership, supported
verbs, host requirements, destructive risk, or secret handling THEN you SHALL
update only the matching matrix surface fields.

WHEN a surface is host-limited THEN you SHALL still set each environment
compatibility field (`package`, `desktop`, `graph`, `officeScript`,
`tomFabric`) to the current state for that backend: `supported`, `partial`,
`preserve-only`, `planned`, `not-required`, or `not-applicable`.

WHEN a backend works only with a required local app, tenant runtime, driver,
trust setting, or API permission THEN you SHALL put the backend state in the
matching environment compatibility field and put the condition in
`hostRequirements`.

WHEN a feature is implemented but not fully covered by tests THEN you SHALL
leave its `supportLevel` as `partial`, `host-limited`, `preserve-only`, or
`planned` as appropriate; you SHALL NOT mark it `supported`.

WHEN marking a surface `supported` THEN you SHALL add direct
`evidenceSelectors` for tests that exercise the claimed operation and verify
readback or an honest host/API limitation.

WHEN a surface cannot be safely mutated through an available API THEN you
SHALL represent it as `host-limited`, `preserve-only`, or `planned` in the
matrix and expose `plan`, `inspect`, or `preserve` behavior instead of
claiming CRUD.

WHEN credentials, tenant tokens, privacy labels, provider auth, or connection
secret state are involved THEN you SHALL document runtime-only or preserve-only
handling in the matrix `secretPolicy`; you SHALL NOT commit or serialize that
material into fixtures, manifests, logs, evidence selectors, or docs.

WHEN adding a direct command, manifest surface, or backend adapter THEN you
SHALL ensure `workbook capabilities --deep` derives the same route and support
metadata from the matrix rather than from hard-coded parallel tables.

WHEN retiring or renaming a command or backend route THEN you SHALL update the
matrix first, then update code, tests, and docs to match it.

Before considering a capability checked off, all of the following must be true:

- The relevant matrix surface has the correct `operations`, backend lane
  fields, `route`, `supportLevel`, `hostRequirements`, `secretPolicy`,
  `destructiveRisk`, and `evidenceSelectors`.
- Every selector in `evidenceSelectors` names an existing committed test.
- `test_capability_matrix_maps_surfaces_to_existing_tests_and_honest_routes`
  and `test_capability_matrix_declares_all_surfaces_with_routes_and_evidence`
  pass.
- The implementation response reports the backend used, operation requested,
  changed state, readback evidence, warnings or limitations, and redacted or
  runtime-only secret handling where applicable.

## Pre-Commit Checks

Normal workbook users do not run the Excel Foundry test suite. The suite is a
developer validation surface for the skill package.

WHEN documenting developer test policy THEN you SHALL keep it in this file or
another maintainer-only document.

You SHALL NOT put developer test policy, live readiness commands, fixture
maintenance rules, or local corpus setup in `SKILL.md` or normal
agent-facing references.

Default developer discovery should exercise as much live behavior as the host
can support while keeping generated/disposable workbooks and preserving clear
host-prerequisite signals.

WHEN Excel COM is installed and responsive THEN default developer discovery
SHALL run live desktop workbook tests without requiring opt-in environment
variables.

WHEN Excel COM is unavailable THEN developer tests SHALL still verify
package-supported behavior and SHALL make it clear that full live Excel
validation could not run because Excel is unavailable.

WHEN a test needs a workbook fixture THEN it SHALL generate a disposable
synthetic workbook or use committed non-binary fixture artifacts.

You SHALL NOT commit workbook binaries, user-local workbook paths, external
corpus contents, or evidence artifacts.

The live capability matrix test is part of default developer discovery. It
uses disposable workbooks and should probe every matrix operation, returning
real execution evidence when the backend is available and structured
limitation evidence when a host or cloud prerequisite is absent.

Before considering Excel Foundry changes complete, run the relevant subset:

```powershell
python -m py_compile plugins/excel-foundry/skills/excel-foundry/scripts/excel_workbook_sync.py plugins/excel-foundry/skills/excel-foundry/scripts/excel_workbook_package.py
python -m unittest discover -s plugins/excel-foundry/skills/excel-foundry/tests -p test_*.py
python <codex-home>/skills/.system/skill-creator/scripts/quick_validate.py plugins/excel-foundry/skills/excel-foundry
```

Before committing, scan for sensitive identifiers:

```powershell
rg -n -i "<sensitive-patterns-for-this-skill>" plugins/excel-foundry/skills/excel-foundry
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

WHEN tests need expanded local corpus coverage THEN they SHALL read roots from
environment variables such as `EXCEL_SYNC_EXTERNAL_ROOTS`.

WHEN `EXCEL_SYNC_EXTERNAL_ROOTS` is absent THEN default external smoke tests
SHALL generate a disposable corpus instead of skipping.

WHEN explicit external roots are provided but contain no workbook files THEN
tests SHALL fail with a clear configuration error.

External smoke tests generate a disposable temp corpus by default, including a
package-readable workbook and flat export files. `EXCEL_SYNC_EXTERNAL_ROOTS`
expands coverage with caller-provided roots but is not a prerequisite for
default developer discovery.

The live generic COM audit test creates its own disposable `.xlsm` with
workbook queries and VBA components at runtime before extracting through COM.
It does not depend on a committed or user-local macro-enabled workbook.


