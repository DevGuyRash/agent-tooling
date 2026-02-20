#!/usr/bin/env sh
set -eu

SKILL_DIR="$(
  unset CDPATH
  cd -- "$(dirname -- "$0")/.." && pwd
)"

while IFS= read -r f; do
  [ -n "$f" ] || continue
  if [ ! -f "$f" ]; then
    echo "FAIL missing file: $f"
    exit 1
  fi
done <<EOF
$SKILL_DIR/SKILL.md
$SKILL_DIR/references/dynamic-form-contract.md
$SKILL_DIR/references/patterns-and-antipatterns.md
$SKILL_DIR/references/examples.md
$SKILL_DIR/references/clipboard-latency.md
$SKILL_DIR/references/example-dynamic-form.yml
$SKILL_DIR/scripts/scaffold_dynamic_form.py
$SKILL_DIR/scripts/lint_dynamic_form_yaml.py
EOF

python3 "$SKILL_DIR/scripts/scaffold_dynamic_form.py" \
  --provider demo \
  --fields secret,input_mode \
  --operation layout \
  --format all >/dev/null

python3 "$SKILL_DIR/scripts/lint_dynamic_form_yaml.py" \
  "$SKILL_DIR/references/example-dynamic-form.yml" >/dev/null

echo "OK skill examples validated"
