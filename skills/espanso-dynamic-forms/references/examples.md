# Examples

## Example A: Minimal dynamic provider

YAML flow (two-stage):
```yaml
- name: form1
  type: form
  params:
    layout: |
      Operation:
      [[operation]]

      Provider:
      [[provider]]

- name: layout_generator
  type: script
  params:
    args:
      - "%CONFIG%/tools/rust/bin/espanso_env"
      - ESPANSO_FORM_OPERATION={{form1.operation}}
      - ESPANSO_FORM_PROVIDER={{form1.provider}}
      - "%CONFIG%/tools/rust/bin/my_layout_generator"

- name: form2
  type: form
  params:
    layout: "{{layout_generator}}"
```

## Example B: Provider with fields

Additional args:
```yaml
- ESPANSO_FORM_FIELD_secret={{form1.secret}}
- ESPANSO_FORM_FIELD_input_mode={{form1.input_mode}}
```

Provider reads:
- `field("secret")`
- `field("input_mode")`

## Example C: Latency-safe output

Recommended modes:
- direct replacement payloads: `print_only`
- optional clipboard side effects: best-effort async write
- avoid status-only payload strings in replacements
