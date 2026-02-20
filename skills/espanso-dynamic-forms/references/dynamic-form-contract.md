# Dynamic Form Contract

## Keys

Required:
- `ESPANSO_FORM_OPERATION` (recommended values: `layout`, `preview`)
- `ESPANSO_FORM_PROVIDER` (provider id, e.g. `html-trunc`, `crypto`, `eventargs`)

Optional:
- `ESPANSO_FORM_FIELD_<name>` (provider-specific values)

## Generator obligations

A conforming dynamic-form generator should:
1. parse operation/provider
2. validate supported operation/provider pair
3. read provider fields as needed
4. print layout text to stdout only
5. return non-zero on invalid input and print error to stderr

## Field naming conventions

- Use lowercase snake_case for `<name>`.
- Keep names stable after release.
- Reserve `operation` and `provider` for top-level keys only.

## YAML pattern

Two-stage pattern:
1. collect context in `form1`
2. call generator in `layout_generator`
3. render `form2` with `layout: "{{layout_generator}}"`

Args pattern:
- `%CONFIG%/.../espanso_env` or equivalent wrapper
- `ESPANSO_FORM_OPERATION=...`
- `ESPANSO_FORM_PROVIDER=...`
- optional `ESPANSO_FORM_FIELD_<name>=...`
- `<layout-generator-binary-or-script>`
