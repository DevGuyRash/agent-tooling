# CLI Implementation Guide

This reference codifies the progressive-disclosure CLI pattern used by the
skill-auditor. Skill authors can follow this pattern; the auditor checks
other skills' CLIs against it (D22).

The CLI is not the audit. It is a just-in-time router that helps an agent
discover the next phase, the current step, the relevant domain, and the report
workflow without loading everything at once.

---

## Architecture pattern

A single POSIX shell script + TOML manifest + markdown content extraction:

- **Shell script** (`scripts/<cli-name>`): Routes subcommands to handler
  functions. Reads structured metadata from TOML, extracts detailed content
  from markdown references on demand.
- **TOML manifest** (`scripts/<cli-name>.toml`): Phases, domains, activation
  rules, hints, step listings — small structured data.
- **Markdown references** (`references/*.md`): Full domain specs, phase
  procedures, scoring rules — the single source of truth for detailed content.

---

## TOML manifest structure

Required sections:

| Section | Purpose |
|---------|---------|
| `[meta]` | Version, name, description |
| `[phases.*]` | Phase ID, name, budget, brief, reference file, heading |
| `[domains.*]` | Domain ID, name, tier, brief, reference, script, activation, hint |
| `[activation]` | Trait-to-domain mapping (trait = "D1, D2, ...") |
| `[steps.*]` | Ordered step list with title, brief, command, and next command |
| `[scripts]` | Script name-to-path mapping |

Supported TOML subset (parseable with `sed`/`awk`):
- `[section]` and `[section.subsection]` headers
- `key = "value"` (string values)
- Comments with `#`

No nested tables, inline tables, or datetime types needed.

---

## Command design rules

| Pattern | Rule |
|---------|------|
| No args | Print usage showing all available commands |
| Listing commands | List all items in each enumerable set (phases, domains, modes) |
| Detail commands | Show full spec for one item (phase N, domain D8) |
| `next-steps` | Guided workflow — ordered list of what to do |
| `step <N>` | Current-step guidance with the next recommended command |
| `report-workflow` | How to turn gathered evidence into a finished report |
| `hints <ID>` | Contextual help for a specific domain or phase |
| `check <name> <dir>` | Run one deterministic check script |
| `check-all <dir>` | Run ALL check scripts, report per-script pass/fail |
| `self-check` | Run all scripts against the skill itself |
| `--format json` | Machine-readable output on listing commands |
| `version` | Print version info |

---

## Output contract

- All commands SHALL produce output under 4KB by default (D10 compliance).
- Listing commands SHALL support `--format json` for machine consumption.
- Workflow commands (`next-steps`, `step <N>`) SHALL support `--format json`.
- `check-all` SHALL report per-script pass/fail with a final summary line.
- `check-all` SHALL exit non-zero when any sub-script fails.
- `report-workflow` SHALL explain how findings, severities, and confidence
  roll into the report. It SHALL NOT pretend helper-script output is the full audit.

---

## TOML parsing

Minimal POSIX parser functions (no external dependencies):

- `toml_get_value(file, section, key)` — Extract `key = "value"` from
  `[section]` using `sed` section isolation + `grep` key match.
- `toml_list_sections(file, prefix)` — List `[prefix.*]` subsection names
  using `grep` + `sed`.

These use only `sed`, `awk`, and `grep` — all POSIX standard.

---

## Markdown extraction pattern

Extract sections by heading from reference files:

```
md_extract_section(file, heading):
    1. Find the line containing the heading text
    2. Record the heading level (number of # characters)
    3. Output all lines until a heading of equal or higher level
```

This makes the CLI a router and markdown the content — single source of
truth with no duplication between TOML metadata and markdown content.

---

## Fallback pattern

SKILL.md SHALL document both the CLI command and the fallback reference:

```markdown
You SHALL run <skills-file-root>/scripts/<cli> <command> for guidance.
IF the CLI is unavailable, read references/<file>.md instead.
```

The CLI and the reference file deliver the same information via different
mechanisms. The reference is the authoritative source; the CLI extracts
from it. This keeps the agent workflow self-documenting without turning the
CLI into a second copy of the full audit instructions.

---

## POSIX compliance rules

- Shebang: `#!/usr/bin/env sh`
- No bashisms: no `[[ ]]`, no arrays, no `local` outside functions
- No GNU-specific flags: no `sed -i` without backup, no `grep -P`,
  no `readlink -f`
- No external dependencies beyond POSIX utilities (`sed`, `awk`, `grep`,
  `sort`, `tr`, `cut`, `wc`, `cat`, `printf`, `find`)
- Argument handling via `case`/positional params, never `eval "$@"`

---

## Config format preference

| Format | Use for |
|--------|---------|
| TOML | Structured metadata (routing, activation rules, hints) |
| JSON | Optional machine-readable output format (`--format json`) |
| Markdown | Detailed content (domain specs, phase procedures, templates) |
| YAML | Avoid for CLI-parsed data (fragile to parse in shell) |
