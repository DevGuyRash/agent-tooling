#!/usr/bin/env bash
# score.sh <run-dir> [out.csv]
# Mechanical scoring for every .svg/.html under run-dir: layer-1/3 proxies
# from validate_svg.py and a layer-2 render attempt via render_preview.sh.
# Layers 4–6 are reviewer-scored per rubric.md; append those columns to the
# CSV afterwards.
set -u

dir="${1:?usage: score.sh <run-dir> [out.csv]}"
out="${2:-$dir/results.csv}"
here="$(cd "$(dirname "$0")" && pwd)"
val="$here/../scripts/validate_svg.py"
render="$here/../scripts/render_preview.sh"

echo "file,parse_l1,validator_errors_l3,validator_warnings,render_l2,notes" > "$out"

find "$dir" -type f \( -name '*.svg' -o -name '*.html' \) | LC_ALL=C sort | while IFS= read -r fpath; do
  parse="pass"; errs="na"; warns="na"; rend="unavailable"; note=""

  if command -v python3 >/dev/null 2>&1; then
    o="$(python3 "$val" "$fpath" 2>&1 || true)"
    errs="$(printf '%s\n' "$o" | grep -c '^\[ERROR\]' || true)"
    warns="$(printf '%s\n' "$o" | grep -c '^\[warn\]' || true)"
    if printf '%s\n' "$o" | grep -q 'XML parse failure'; then parse="fail"; fi
    if printf '%s\n' "$o" | grep -q 'needs <!DOCTYPE'; then parse="fail"; fi
  else
    note="python3 missing — validator skipped"
  fi

  png="$(mktemp -u /tmp/score-XXXXXX).png"
  if "$render" "$fpath" "$png" >/dev/null 2>&1; then
    rend="pass"
  else
    rc=$?
    if [ "$rc" -eq 2 ]; then rend="unavailable"; else rend="fail"; fi
  fi
  rm -f "$png" 2>/dev/null

  echo "$fpath,$parse,$errs,$warns,$rend,$note" >> "$out"
done

echo "$out"
