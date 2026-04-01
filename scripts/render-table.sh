#!/bin/sh
set -eu

# render-table.sh — General-purpose Unicode box-drawing table renderer.
# Reads tabular data from stdin or file, auto-detects format, outputs a
# properly aligned box-drawing table. Zero domain knowledge.

print_help() {
  cat <<'EOF'
render-table.sh — Unicode box-drawing table renderer

Usage:
  sh render-table.sh [OPTIONS] [FILE]
  ... | sh render-table.sh [OPTIONS]

Renders tabular data as a Unicode box-drawing table. Reads from FILE or
stdin. Auto-detects input format when no format flag is given.

Input formats (auto-detected if omitted):
  --tsv           TSV — tab-separated values (first line = headers)
  --csv           CSV — RFC 4180 (quoted fields, embedded commas)
  --jsonl         JSONL — one JSON object per line (requires jq)
  --json          JSON — array of objects (requires jq)
  --yaml          YAML — list of objects (requires python3 + PyYAML)

Options:
  --file PATH         Read input from PATH instead of stdin
  --fields F1,F2,...  Select and order fields (JSON/JSONL/YAML; optional —
                      auto-discovered from first object when omitted)
  --headers H1,H2,... Display headers (overrides field names / first row)
  --max-col-width N   Max display columns per column before wrapping (0 = no limit)
  --max-width N       Max total table width in display columns (0 = no limit)
  --col-widths W,...  Per-column widths (e.g. "10,,30"); empty = auto
  --help, -h          Show this help

Examples:
  sh render-table.sh data.tsv
  sh render-table.sh --file data.csv
  cat data.csv | sh render-table.sh
  echo '[{"a":1}]' | sh render-table.sh
  echo '{"a":1}' | sh render-table.sh --fields a
  sh render-table.sh --yaml data.yml --headers "Name,Age"
EOF
}

hint() {
  printf 'render-table.sh: %s\n' "$*" >&2
}

# ── Argument parsing ─────────────────────────────────────────────────

mode=auto
fields=
headers=
max_col_width=0
max_width=0
col_widths=
input_file=
positional=

while [ $# -gt 0 ]; do
  case "$1" in
    --tsv)           mode=tsv; shift ;;
    --csv)           mode=csv; shift ;;
    --jsonl)         mode=jsonl; shift ;;
    --json)          mode=json; shift ;;
    --yaml)          mode=yaml; shift ;;
    --file)          input_file=${2-}; shift 2 ;;
    --fields)        fields=${2-}; shift 2 ;;
    --headers)       headers=${2-}; shift 2 ;;
    --max-col-width) max_col_width=${2-}; shift 2 ;;
    --max-width)     max_width=${2-}; shift 2 ;;
    --col-widths)    col_widths=${2-}; shift 2 ;;
    --help|-h)       print_help; exit 0 ;;
    -*)              hint "unknown option: $1. Run with --help to see available options."; exit 1 ;;
    *)
      # Positional argument — treat as file path
      if [ -z "$positional" ]; then
        positional=$1; shift
      else
        hint "unexpected argument: $1. Only one input file can be specified."; exit 1
      fi
      ;;
  esac
done

# Resolve input file from positional or --file
if [ -n "$positional" ] && [ -n "$input_file" ]; then
  hint "both --file and a positional file argument were given. Use one or the other."
  exit 1
fi
if [ -n "$positional" ]; then
  input_file=$positional
fi

# ── Input acquisition ────────────────────────────────────────────────

tmpfile=
cleanup() { rm -f ${tmpfile:+"$tmpfile"}; }
trap cleanup EXIT HUP INT TERM

if [ -n "$input_file" ]; then
  if [ ! -f "$input_file" ]; then
    hint "file not found: $input_file"
    exit 1
  fi
  # Copy to temp so all code paths read from the same place
  tmpfile=$(mktemp)
  cat "$input_file" > "$tmpfile"
elif [ -t 0 ]; then
  # Stdin is a TTY with no file — show help
  print_help
  exit 0
else
  # Buffer stdin
  tmpfile=$(mktemp)
  cat > "$tmpfile"
fi

# Check for empty input
if [ ! -s "$tmpfile" ]; then
  exit 0
fi

# ── Auto-format detection ───────────────────────────────────────────

if [ "$mode" = "auto" ]; then
  first_line=$(head -1 "$tmpfile")
  case "$first_line" in
    '['*)
      mode=json
      hint "auto-detected JSON array input"
      ;;
    '{'*)
      mode=jsonl
      hint "auto-detected JSONL input"
      ;;
    '---'*|'- '*)
      mode=yaml
      hint "auto-detected YAML input"
      ;;
    *)
      if printf '%s' "$first_line" | grep -q '	'; then
        mode=tsv
      elif printf '%s' "$first_line" | grep -q ','; then
        mode=csv
      else
        mode=tsv
      fi
      ;;
  esac
fi

# ── Dependency checks ───────────────────────────────────────────────

case "$mode" in
  jsonl|json)
    if ! command -v jq >/dev/null 2>&1; then
      hint "--$mode requires jq. Install: https://jqlang.github.io/jq/download/"
      exit 1
    fi
    ;;
  yaml)
    if ! command -v python3 >/dev/null 2>&1; then
      hint "--yaml requires python3. Install Python 3 from https://python.org"
      exit 1
    fi
    if ! python3 -c "import yaml" 2>/dev/null; then
      hint "--yaml requires PyYAML. Install: pip install pyyaml"
      exit 1
    fi
    ;;
esac

# ── Auto-discover fields for JSON-family formats ────────────────────

auto_discover_fields() {
  case "$mode" in
    jsonl)
      fields=$(head -1 "$tmpfile" | jq -r 'keys | join(",")')
      ;;
    json)
      fields=$(jq -r 'if length == 0 then "" else .[0] | keys | join(",") end' "$tmpfile")
      ;;
    yaml)
      fields=$(python3 -c "
import yaml, sys
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
    print(','.join(data[0].keys()))
elif isinstance(data, dict):
    print(','.join(data.keys()))
" "$tmpfile")
      ;;
  esac
  if [ -n "$fields" ]; then
    hint "auto-discovered fields: $fields"
  fi
}

case "$mode" in
  jsonl|json|yaml)
    if [ -z "$fields" ]; then
      auto_discover_fields
    fi
    if [ -z "$fields" ]; then
      # Empty result set (e.g. []) — exit cleanly like empty stdin
      exit 0
    fi
    ;;
esac

# ── Stage 1: Normalize any input format to TSV ──────────────────────

csv_to_tsv() {
  awk '
    BEGIN { partial = "" }
    {
      if (partial != "") partial = partial "\n" $0
      else               partial = $0

      if (!record_complete(partial)) next

      n = parse_record(partial, flds)
      for (i = 1; i <= n; i++) {
        if (i > 1) printf "\t"
        gsub(/[\t\r]/, " ", flds[i])
        gsub(/\n/, " ", flds[i])
        printf "%s", flds[i]
      }
      printf "\n"
      partial = ""
    }
    END {
      if (partial != "") {
        n = parse_record(partial, flds)
        for (i = 1; i <= n; i++) {
          if (i > 1) printf "\t"
          gsub(/[\t\n\r]/, " ", flds[i])
          printf "%s", flds[i]
        }
        printf "\n"
      }
    }
    function record_complete(rec,    i, in_q, c, len) {
      in_q = 0; len = length(rec)
      for (i = 1; i <= len; i++) {
        c = substr(rec, i, 1)
        if (c == "\"") {
          if (in_q && i < len && substr(rec, i + 1, 1) == "\"") i++
          else in_q = !in_q
        }
      }
      return !in_q
    }
    function parse_record(rec, result,    i, c, field, in_q, pos, len) {
      split("", result)
      len = length(rec); pos = 1; i = 0
      while (1) {
        i++; field = ""; in_q = 0
        if (pos <= len && substr(rec, pos, 1) == "\"") {
          in_q = 1; pos++
          while (pos <= len) {
            c = substr(rec, pos, 1)
            if (c == "\"") {
              if (pos < len && substr(rec, pos + 1, 1) == "\"") {
                field = field "\""; pos += 2
              } else { pos++; break }
            } else { field = field c; pos++ }
          }
          if (pos <= len && substr(rec, pos, 1) == ",") pos++
        } else {
          while (pos <= len) {
            c = substr(rec, pos, 1)
            if (c == ",") { pos++; break }
            field = field c; pos++
          }
        }
        result[i] = field
        if (pos > len) {
          if (len > 0 && substr(rec, len, 1) == "," && !in_q) {
            i++; result[i] = ""
          }
          break
        }
      }
      return i
    }
  '
}

jsonl_to_tsv() {
  # Header line
  if [ -n "$headers" ]; then
    printf '%s\n' "$headers" | tr ',' '\t'
  else
    printf '%s\n' "$fields" | tr ',' '\t'
  fi
  # Build jq filter
  jq_expr="["
  first=1
  saved_ifs=$IFS; IFS=','
  for f in $fields; do
    if [ "$first" = 1 ]; then first=0; else jq_expr="$jq_expr,"; fi
    jq_expr="$jq_expr (.\"$f\" // \"\" | if type == \"array\" then (map(tostring) | join(\",\")) elif type == \"object\" then tojson else tostring end)"
  done
  IFS=$saved_ifs
  jq_expr="$jq_expr] | @tsv"
  jq -r "$jq_expr"
}

json_to_jsonl() {
  jq -c '.[]'
}

yaml_to_jsonl() {
  python3 -c "
import yaml, json, sys
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
if isinstance(data, list):
    for item in data:
        print(json.dumps(item, ensure_ascii=False))
elif isinstance(data, dict):
    print(json.dumps(data, ensure_ascii=False))
" "$tmpfile"
}

normalize_to_tsv() {
  case "$mode" in
    tsv)   cat "$tmpfile" ;;
    csv)   cat "$tmpfile" | csv_to_tsv ;;
    jsonl) cat "$tmpfile" | jsonl_to_tsv ;;
    json)  json_to_jsonl < "$tmpfile" | jsonl_to_tsv ;;
    yaml)  yaml_to_jsonl | jsonl_to_tsv ;;
  esac
}

# ── Stage 2: Header override (TSV/CSV only; JSON-family handles above)

apply_header_override() {
  if [ -n "$headers" ] && [ "$mode" = "tsv" -o "$mode" = "csv" ]; then
    if read -r _discarded; then
      printf '%s\n' "$headers" | tr ',' '\t'
      cat
    fi
  else
    cat
  fi
}

# ── Stage 3: Render box-drawing table ───────────────────────────────
# Uses Python when available (correct CJK/emoji display width via
# unicodedata.east_asian_width). Falls back to awk for ASCII content.

render_box_table_python() {
  python3 -c '
import sys, unicodedata

def dwidth(s):
    """Display width: 2 for fullwidth/wide chars, 1 for everything else."""
    w = 0
    for c in s:
        eaw = unicodedata.east_asian_width(c)
        w += 2 if eaw in ("F", "W") else 1
    return w

def dwidth_wrap(text, width):
    """Word-wrap text to fit within display-width columns. Returns list of lines."""
    if dwidth(text) <= width:
        return [text]
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        ww = dwidth(word)
        cw = dwidth(cur)
        if cw == 0:
            if ww > width:
                # Hard-break long word
                rem = word
                while dwidth(rem) > width:
                    # Find the split point by character
                    cut = ""
                    for ch in rem:
                        if dwidth(cut + ch) > width:
                            break
                        cut += ch
                    if not cut:
                        cut = rem[0]  # At least one char
                    lines.append(cut)
                    rem = rem[len(cut):]
                cur = rem
            else:
                cur = word
        elif cw + 1 + ww <= width:
            cur = cur + " " + word
        else:
            lines.append(cur)
            if ww > width:
                rem = word
                while dwidth(rem) > width:
                    cut = ""
                    for ch in rem:
                        if dwidth(cut + ch) > width:
                            break
                        cut += ch
                    if not cut:
                        cut = rem[0]
                    lines.append(cut)
                    rem = rem[len(cut):]
                cur = rem
            else:
                cur = word
    if cur:
        lines.append(cur)
    return lines if lines else [""]

def pad(s, width):
    """Right-pad string to display width."""
    return s + " " * (width - dwidth(s))

# Read TSV from stdin
rows = []
for line in sys.stdin:
    rows.append(line.rstrip("\n").split("\t"))

if len(rows) <= 1:
    sys.exit(0)  # Header-only or empty

# Normalize column count
ncols = max(len(r) for r in rows)
for r in rows:
    while len(r) < ncols:
        r.append("")

# Read parameters
mcw = int(sys.argv[1]) if len(sys.argv) > 1 else 0
mw  = int(sys.argv[2]) if len(sys.argv) > 2 else 0
col_widths_arg = sys.argv[3] if len(sys.argv) > 3 else ""

# Parse per-column width overrides
explicit_cw = {}
if col_widths_arg:
    for i, w in enumerate(col_widths_arg.split(",")):
        w = w.strip()
        if w:
            explicit_cw[i] = int(w)

# Compute column widths
cw = [0] * ncols
for c in range(ncols):
    if c in explicit_cw:
        cw[c] = explicit_cw[c]
    else:
        cw[c] = max((dwidth(r[c]) for r in rows), default=1)
        if mcw > 0 and cw[c] > mcw:
            cw[c] = mcw
    if cw[c] < 1:
        cw[c] = 1

# Apply max total width
if mw > 0:
    overhead = 1 + 3 * ncols
    budget = mw - overhead
    if budget < ncols:
        budget = ncols
    total = sum(cw)
    if total > budget:
        ratio = budget / total
        cw = [max(1, int(w * ratio)) for w in cw]

# Box-drawing characters
def border(pos):
    if   pos == "top": left, fill, mid, right = "\u250c", "\u2500", "\u252c", "\u2510"
    elif pos == "mid": left, fill, mid, right = "\u251c", "\u2500", "\u253c", "\u2524"
    else:              left, fill, mid, right = "\u2514", "\u2500", "\u2534", "\u2518"
    parts = [left]
    for c in range(ncols):
        parts.append(fill * (cw[c] + 2))
        parts.append(mid if c < ncols - 1 else right)
    print("".join(parts))

def render_row(r):
    # Wrap each cell
    wrapped = [dwidth_wrap(r[c], cw[c]) for c in range(ncols)]
    max_lines = max(len(w) for w in wrapped)
    for ln in range(max_lines):
        parts = ["\u2502"]
        for c in range(ncols):
            cell = wrapped[c][ln] if ln < len(wrapped[c]) else ""
            parts.append(" " + pad(cell, cw[c]) + " \u2502")
        print("".join(parts))

# Render
border("top")
render_row(rows[0])
if len(rows) > 1:
    border("mid")
    for i, r in enumerate(rows[1:], 1):
        render_row(r)
        if i < len(rows) - 1:
            border("mid")
border("bot")
' "$max_col_width" "$max_width" "$col_widths"
}

render_box_table_awk() {
  awk -v mcw="$max_col_width" -v mw="$max_width" -v cws="$col_widths" '
BEGIN { FS = "\t"; nr = 0; nc = 0 }

{
  nr++
  if (NF > nc) nc = NF
  for (i = 1; i <= NF; i++) d[nr, i] = $i
}

END {
  if (nr <= 1) exit 0

  for (r = 1; r <= nr; r++)
    for (c = 1; c <= nc; c++)
      if (!((r SUBSEP c) in d)) d[r, c] = ""

  # Parse per-column width overrides
  if (cws != "") {
    n_cws = split(cws, cws_arr, ",")
    for (i = 1; i <= n_cws; i++) {
      v = cws_arr[i] + 0
      if (v > 0) explicit_cw[i] = v
    }
  }

  for (c = 1; c <= nc; c++) {
    if (c in explicit_cw) {
      cw[c] = explicit_cw[c]
    } else {
      cw[c] = 0
      for (r = 1; r <= nr; r++) {
        l = length(d[r, c])
        if (l > cw[c]) cw[c] = l
      }
      if (mcw > 0 && cw[c] > mcw) cw[c] = mcw
    }
    if (cw[c] < 1) cw[c] = 1
  }

  if (mw > 0) {
    overhead = 1 + 3 * nc
    budget = mw - overhead
    if (budget < nc) budget = nc
    total = 0
    for (c = 1; c <= nc; c++) total += cw[c]
    if (total > budget) {
      for (c = 1; c <= nc; c++) {
        cw[c] = int(cw[c] * budget / total)
        if (cw[c] < 1) cw[c] = 1
      }
    }
  }

  draw_border("top")
  draw_row(1)
  if (nr > 1) {
    draw_border("mid")
    for (r = 2; r <= nr; r++) {
      draw_row(r)
      if (r < nr) draw_border("mid")
    }
  }
  draw_border("bot")
}

function draw_border(pos,    c, i, s, left, fill, mid, right) {
  if      (pos == "top") { left = "\342\224\214"; mid = "\342\224\254"; right = "\342\224\220" }
  else if (pos == "mid") { left = "\342\224\234"; mid = "\342\224\274"; right = "\342\224\244" }
  else                   { left = "\342\224\224"; mid = "\342\224\264"; right = "\342\224\230" }
  fill = "\342\224\200"
  s = left
  for (c = 1; c <= nc; c++) {
    for (i = 1; i <= cw[c] + 2; i++) s = s fill
    s = s (c < nc ? mid : right)
  }
  printf "%s\n", s
}

function draw_row(r,    c, max_lines, nl, l, cell, line) {
  max_lines = 1
  for (c = 1; c <= nc; c++) {
    nl = word_wrap(d[r, c], cw[c], c)
    wl[c] = nl
    if (nl > max_lines) max_lines = nl
  }
  for (l = 1; l <= max_lines; l++) {
    line = "\342\224\202"
    for (c = 1; c <= nc; c++) {
      cell = (l <= wl[c]) ? wd[c, l] : ""
      line = line " " pad(cell, cw[c]) " \342\224\202"
    }
    printf "%s\n", line
  }
}

function word_wrap(text, width, col,    nw, words, i, ln, line, wlen, llen, rem) {
  for (i in wd) {
    split(i, _idx, SUBSEP)
    if (_idx[1] == col) delete wd[i]
  }
  if (length(text) <= width) { wd[col, 1] = text; return 1 }
  nw = split(text, words, " ")
  line = ""; ln = 0
  for (i = 1; i <= nw; i++) {
    wlen = length(words[i]); llen = length(line)
    if (llen == 0) {
      if (wlen > width) {
        rem = words[i]
        while (length(rem) > width) { ln++; wd[col, ln] = substr(rem, 1, width); rem = substr(rem, width + 1) }
        line = rem
      } else { line = words[i] }
    } else if (llen + 1 + wlen <= width) { line = line " " words[i] }
    else {
      ln++; wd[col, ln] = line
      if (wlen > width) {
        rem = words[i]
        while (length(rem) > width) { ln++; wd[col, ln] = substr(rem, 1, width); rem = substr(rem, width + 1) }
        line = rem
      } else { line = words[i] }
    }
  }
  if (length(line) > 0) { ln++; wd[col, ln] = line }
  if (ln == 0) { wd[col, 1] = ""; return 1 }
  return ln
}

function pad(str, width,    i, p) {
  p = str
  for (i = length(str); i < width; i++) p = p " "
  return p
}
'
}

render_box_table() {
  if command -v python3 >/dev/null 2>&1; then
    render_box_table_python
  else
    render_box_table_awk
  fi
}

# ── Pipeline ─────────────────────────────────────────────────────────

normalize_to_tsv | apply_header_override | render_box_table
