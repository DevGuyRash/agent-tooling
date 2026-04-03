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
  --fit-mode MODE     Width fit strategy: drop-last-then-shrink (default)
                      or shrink
  --min-col-width N   Minimum width to preserve for auto-sized columns before
                      columns start dropping (default: 12)
  --min-columns N     Minimum number of leading columns to keep visible when
                      dropping columns to fit width (default: 1)
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
fit_mode=drop-last-then-shrink
min_col_width=12
min_columns=1
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
    --fit-mode)      fit_mode=${2-}; shift 2 ;;
    --min-col-width) min_col_width=${2-}; shift 2 ;;
    --min-columns)   min_columns=${2-}; shift 2 ;;
    --help|-h)       print_help; exit 0 ;;
    -*)              hint "unknown option: $1. Run with --help to see available options."; exit 1 ;;
    *)
      if [ -z "$positional" ]; then
        positional=$1; shift
      else
        hint "unexpected argument: $1. Only one input file can be specified."; exit 1
      fi
      ;;
  esac
done

case "$fit_mode" in
  shrink|drop-last-then-shrink) ;;
  *)
    hint "unsupported fit mode: $fit_mode. Expected shrink or drop-last-then-shrink."
    exit 1
    ;;
esac

case "$min_col_width" in
  ''|*[!0-9]*)
    hint "--min-col-width expects a non-negative integer."
    exit 1
    ;;
esac

case "$min_columns" in
  ''|*[!0-9]*)
    hint "--min-columns expects a non-negative integer."
    exit 1
    ;;
esac

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
  tmpfile=$(mktemp)
  cat "$input_file" > "$tmpfile"
elif [ -t 0 ]; then
  print_help
  exit 0
else
  tmpfile=$(mktemp)
  cat > "$tmpfile"
fi

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
  if [ -n "$headers" ]; then
    printf '%s\n' "$headers" | tr ',' '\t'
  else
    printf '%s\n' "$fields" | tr ',' '\t'
  fi

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

render_box_table_python() {
  python3 -c '
import sys
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def dwidth(text):
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in ("F", "W") else 1
    return width


def normalize_text(text):
    try:
        return text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    except Exception:
        return text


def dwidth_wrap(text, width):
    if width <= 0 or dwidth(text) <= width:
        return [text]
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        word_width = dwidth(word)
        current_width = dwidth(current)
        if current_width == 0:
            if word_width <= width:
                current = word
                continue
            remaining = word
            while dwidth(remaining) > width:
                cut = ""
                for ch in remaining:
                    if dwidth(cut + ch) > width:
                        break
                    cut += ch
                if not cut:
                    cut = remaining[0]
                lines.append(cut)
                remaining = remaining[len(cut):]
            current = remaining
            continue
        candidate = current + " " + word
        if dwidth(candidate) <= width:
            current = candidate
            continue
        lines.append(current)
        if word_width <= width:
            current = word
            continue
        remaining = word
        while dwidth(remaining) > width:
            cut = ""
            for ch in remaining:
                if dwidth(cut + ch) > width:
                    break
                cut += ch
            if not cut:
                cut = remaining[0]
            lines.append(cut)
            remaining = remaining[len(cut):]
        current = remaining
    if current or not lines:
        lines.append(current)
    return lines


def pad(text, width):
    return text + (" " * max(0, width - dwidth(text)))


def compute_budget(max_width, count):
    overhead = 1 + (3 * count)
    budget = max_width - overhead
    if budget < count:
        budget = count
    return budget


def shrink_widths(visible, natural_widths, explicit_indices, budget, min_floor, allow_emergency):
    widths = {idx: natural_widths[idx] for idx in visible}
    floors = {}
    for idx in visible:
        if allow_emergency:
            floors[idx] = 1
        elif idx in explicit_indices:
            floors[idx] = natural_widths[idx]
        else:
            floors[idx] = min(natural_widths[idx], max(1, min_floor))
    excess = sum(widths.values()) - budget
    while excess > 0:
        candidates = [idx for idx in visible if widths[idx] > floors[idx]]
        if not candidates:
            return widths, False
        candidates.sort(key=lambda idx: (widths[idx], idx), reverse=True)
        for idx in candidates:
            if excess <= 0:
                break
            if widths[idx] > floors[idx]:
                widths[idx] -= 1
                excess -= 1
    return widths, True


rows = [[normalize_text(cell) for cell in line.rstrip("\n").split("\t")] for line in sys.stdin]
if len(rows) <= 1:
    sys.exit(0)

ncols = max(len(row) for row in rows)
for row in rows:
    while len(row) < ncols:
        row.append("")

mcw = int(sys.argv[1]) if len(sys.argv) > 1 else 0
mw = int(sys.argv[2]) if len(sys.argv) > 2 else 0
col_widths_arg = sys.argv[3] if len(sys.argv) > 3 else ""
fit_mode = sys.argv[4] if len(sys.argv) > 4 else "drop-last-then-shrink"
min_col_width = int(sys.argv[5]) if len(sys.argv) > 5 else 12
min_columns = int(sys.argv[6]) if len(sys.argv) > 6 else 1

explicit_widths = {}
if col_widths_arg:
    for idx, raw in enumerate(col_widths_arg.split(",")):
        raw = raw.strip()
        if raw:
            explicit_widths[idx] = max(1, int(raw))

natural_widths = []
for col in range(ncols):
    if col in explicit_widths:
        width = explicit_widths[col]
    else:
        width = max((dwidth(row[col]) for row in rows), default=1)
        if mcw > 0 and width > mcw:
            width = mcw
    natural_widths.append(max(1, width))

visible = list(range(ncols))
dropped = []
widths = {idx: natural_widths[idx] for idx in visible}

if mw > 0 and visible:
    budget = compute_budget(mw, len(visible))
    if fit_mode == "shrink":
        widths, ok = shrink_widths(visible, natural_widths, set(explicit_widths), budget, min_col_width, False)
        if not ok:
            widths, _ = shrink_widths(visible, natural_widths, set(explicit_widths), budget, 1, True)
    else:
        while True:
            budget = compute_budget(mw, len(visible))
            widths, ok = shrink_widths(visible, natural_widths, set(explicit_widths), budget, min_col_width, False)
            if ok:
                break
            if len(visible) > max(1, min_columns):
                dropped_idx = visible.pop()
                dropped.append(rows[0][dropped_idx])
                continue
            widths, _ = shrink_widths(visible, natural_widths, set(explicit_widths), budget, 1, True)
            break

if not visible:
    sys.exit(0)

visible_rows = [[row[idx] for idx in visible] for row in rows]
visible_widths = [widths[idx] for idx in visible]

if dropped:
    print("Columns omitted to fit width: " + ", ".join(dropped))


def border(kind):
    if kind == "top":
        left, fill, mid, right = "\u250c", "\u2500", "\u252c", "\u2510"
    elif kind == "mid":
        left, fill, mid, right = "\u251c", "\u2500", "\u253c", "\u2524"
    else:
        left, fill, mid, right = "\u2514", "\u2500", "\u2534", "\u2518"
    parts = [left]
    for idx, width in enumerate(visible_widths):
        parts.append(fill * (width + 2))
        parts.append(mid if idx < len(visible_widths) - 1 else right)
    print("".join(parts))


def render_row(row):
    wrapped = [dwidth_wrap(row[idx], visible_widths[idx]) for idx in range(len(visible_widths))]
    max_lines = max(len(cell) for cell in wrapped)
    for line_idx in range(max_lines):
        parts = ["\u2502"]
        for idx, width in enumerate(visible_widths):
            cell = wrapped[idx][line_idx] if line_idx < len(wrapped[idx]) else ""
            parts.append(" " + pad(cell, width) + " \u2502")
        print("".join(parts))


border("top")
render_row(visible_rows[0])
border("mid")
for row_index, row in enumerate(visible_rows[1:]):
    render_row(row)
    if row_index < len(visible_rows) - 2:
        border("mid")
border("bot")
' "$max_col_width" "$max_width" "$col_widths" "$fit_mode" "$min_col_width" "$min_columns"
}

render_box_table_awk() {
  awk -v mcw="$max_col_width" -v mw="$max_width" -v cws="$col_widths" -v fit="$fit_mode" -v mincw="$min_col_width" -v mincols="$min_columns" '
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

  if (cws != "") {
    n_cws = split(cws, cws_arr, ",")
    for (i = 1; i <= n_cws; i++) {
      v = cws_arr[i] + 0
      if (v > 0) explicit_cw[i] = v
    }
  }

  for (c = 1; c <= nc; c++) {
    visible[c] = 1
    if (c in explicit_cw) {
      natural[c] = explicit_cw[c]
    } else {
      natural[c] = 0
      for (r = 1; r <= nr; r++) {
        l = length(d[r, c])
        if (l > natural[c]) natural[c] = l
      }
      if (mcw > 0 && natural[c] > mcw) natural[c] = mcw
    }
    if (natural[c] < 1) natural[c] = 1
  }

  visible_count = nc
  dropped_count = 0

  if (mw > 0) {
    while (1) {
      budget = mw - (1 + 3 * visible_count)
      if (budget < visible_count) budget = visible_count

      for (c = 1; c <= nc; c++) {
        if (!visible[c]) continue
        cw[c] = natural[c]
        if (c in explicit_cw) floor[c] = natural[c]
        else {
          floor[c] = natural[c]
          if (mincw > 0 && floor[c] > mincw) floor[c] = mincw
          if (floor[c] < 1) floor[c] = 1
        }
      }

      ok = shrink_to_budget(budget, 0)
      if (ok || fit == "shrink") break

      if (visible_count > mincols) {
        dropped_idx = last_visible()
        dropped[++dropped_count] = d[1, dropped_idx]
        visible[dropped_idx] = 0
        delete cw[dropped_idx]
        delete floor[dropped_idx]
        visible_count--
        continue
      }

      for (c = 1; c <= nc; c++) if (visible[c]) floor[c] = 1
      shrink_to_budget(budget, 1)
      break
    }

    if (fit == "shrink" && !ok) {
      for (c = 1; c <= nc; c++) if (visible[c]) floor[c] = 1
      shrink_to_budget(budget, 1)
    }
  } else {
    for (c = 1; c <= nc; c++) if (visible[c]) cw[c] = natural[c]
  }

  if (dropped_count > 0) {
    note = "Columns omitted to fit width: "
    for (i = 1; i <= dropped_count; i++) {
      if (i > 1) note = note ", "
      note = note dropped[i]
    }
    print note
  }

  draw_border("top")
  draw_row(1)
  draw_border("mid")
  for (r = 2; r <= nr; r++) {
    draw_row(r)
    if (r < nr) draw_border("mid")
  }
  draw_border("bot")
}

function shrink_to_budget(budget, emergency,    total, changed, maxw, c, i, target) {
  total = 0
  for (c = 1; c <= nc; c++) if (visible[c]) total += cw[c]
  while (total > budget) {
    changed = 0
    maxw = 0
    for (c = 1; c <= nc; c++) {
      if (!visible[c]) continue
      if (cw[c] > floor[c] && cw[c] > maxw) maxw = cw[c]
    }
    if (maxw == 0) return 0
    for (c = nc; c >= 1 && total > budget; c--) {
      if (!visible[c]) continue
      if (cw[c] == maxw && cw[c] > floor[c]) {
        cw[c]--
        total--
        changed = 1
      }
    }
    if (!changed) return 0
  }
  return 1
}

function last_visible(    c) {
  for (c = nc; c >= 1; c--) if (visible[c]) return c
  return 0
}

function draw_border(pos,    c, i, s, left, fill, mid, right) {
  if      (pos == "top") { left = "\342\224\214"; mid = "\342\224\254"; right = "\342\224\220" }
  else if (pos == "mid") { left = "\342\224\234"; mid = "\342\224\274"; right = "\342\224\244" }
  else                   { left = "\342\224\224"; mid = "\342\224\264"; right = "\342\224\230" }
  fill = "\342\224\200"
  s = left
  first = 1
  for (c = 1; c <= nc; c++) {
    if (!visible[c]) continue
    for (i = 1; i <= cw[c] + 2; i++) s = s fill
    if (visible_index(c) < visible_count) s = s mid
    else s = s right
  }
  printf "%s\n", s
}

function visible_index(col,    c, idx) {
  idx = 0
  for (c = 1; c <= nc; c++) {
    if (!visible[c]) continue
    idx++
    if (c == col) return idx
  }
  return idx
}

function draw_row(r,    c, max_lines, nl, l, cell, line, idx) {
  max_lines = 1
  for (c = 1; c <= nc; c++) {
    if (!visible[c]) continue
    nl = word_wrap(d[r, c], cw[c], c)
    wl[c] = nl
    if (nl > max_lines) max_lines = nl
  }
  for (l = 1; l <= max_lines; l++) {
    line = "\342\224\202"
    for (c = 1; c <= nc; c++) {
      if (!visible[c]) continue
      cell = (l <= wl[c]) ? wd[c, l] : ""
      line = line " " pad(cell, cw[c]) " \342\224\202"
    }
    printf "%s\n", line
  }
}

function word_wrap(text, width, col,    i, nw, words, ln, line, wlen, llen, rem) {
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
      } else line = words[i]
    } else if (llen + 1 + wlen <= width) {
      line = line " " words[i]
    } else {
      ln++; wd[col, ln] = line
      if (wlen > width) {
        rem = words[i]
        while (length(rem) > width) { ln++; wd[col, ln] = substr(rem, 1, width); rem = substr(rem, width + 1) }
        line = rem
      } else line = words[i]
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

normalize_to_tsv | apply_header_override | render_box_table
