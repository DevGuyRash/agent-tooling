---
name: espanso-dynamic-forms
description: >-
  Build portable dynamic Espanso forms where a script or binary generates form
  layouts at runtime. Use when the task involves: (1) Creating or modifying
  Espanso form triggers or match files, (2) Building dynamic Espanso forms with
  runtime-generated layouts or choices, (3) Scaffolding a new Espanso form
  provider pattern, (4) Configuring Espanso YAML for scripted fields or
  runtime-generated options, (5) Debugging or linting Espanso form
  configurations, (6) Implementing clipboard or output patterns for Espanso
  expansions, or (7) Any task involving Espanso text expansion with dynamic or
  scripted form UIs.
license: MIT
metadata:
  author: DevGuyRash
  version: "1.2.3"
  category: development
---

# Espanso Dynamic Forms

The generator can be Rust, Python, shell, or any runtime that follows the contract.

## Runtime contract

Required keys:

- `ESPANSO_FORM_OPERATION`
- `ESPANSO_FORM_PROVIDER`

Optional provider inputs:

- `ESPANSO_FORM_FIELD_<name>`

Rule:

- layout generator prints only layout text to stdout.

Read first:

- [references/dynamic-form-contract.md](references/dynamic-form-contract.md)

## Workflow

1. Design provider contract and field names.
2. Scaffold starter snippets:

```bash
python3 scripts/scaffold_dynamic_form.py \
  --provider html-trunc \
  --fields html_text,max_items \
  --operation layout \
  --format all
```

3. Implement provider logic in your chosen language.
4. Wire YAML `layout_generator` args to contract keys.
5. Lint YAML contract usage:

```bash
python3 scripts/lint_dynamic_form_yaml.py path/to/match-file.yml --strict
```

## Output and clipboard policy

For low-latency expansions:

- prefer `print_only` when replacement payload is already emitted by the script output
- if clipboard side effects are needed, do best-effort writes outside the critical path
- do not replace user payload with status text like `Copied to clipboard`

Read [references/clipboard-latency.md](references/clipboard-latency.md) for latency behavior, [references/patterns-and-antipatterns.md](references/patterns-and-antipatterns.md) when choosing a form's architecture, and [references/examples.md](references/examples.md) for end-to-end examples.
