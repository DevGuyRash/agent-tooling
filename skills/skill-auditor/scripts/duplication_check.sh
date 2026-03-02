#!/usr/bin/env sh
# skill-auditor — Deterministic duplication detection (D16).
#
# Usage:
#   duplication_check.sh <skill-directory> [--scope operative|advisory|all] \
#     [--format text|json] [--max-hops N]
#
# Detects exact directive duplication, exact instruction-block duplication,
# and contradiction candidates across skill documentation. Findings are tiered:
# operative duplicates gate verdicts, advisory duplicates do not.

set -eu

usage() {
    echo "Usage: duplication_check.sh <skill-directory> [--scope operative|advisory|all] [--format text|json] [--max-hops N]"
    echo ""
    echo "Options:"
    echo "  --scope operative|advisory|all   Which document tier to scan (default: all)"
    echo "  --format text|json               Output format (default: text)"
    echo "  --max-hops N                     Extra markdown reachability hops from SKILL.md (default: 2)"
    echo ""
    echo "Detectors:"
    echo "  - Exact directive-line duplicates (MUST/SHALL/SHOULD/MAY)"
    echo "  - Exact normalized instruction-block duplicates (3+ non-empty lines)"
    echo "  - Contradiction candidates via modality/negation stripping"
}

require_opt_value() {
    opt="$1"
    val="${2-}"
    case "$val" in
        ""|--*)
            echo "error: option $opt requires a value"
            exit 1
            ;;
    esac
}

json_escape() {
    printf '%s' "$1" | awk '
        BEGIN { ORS = "" }
        {
            gsub(/\\/, "\\\\")
            gsub(/"/, "\\\"")
            gsub(/\t/, "\\t")
            gsub(/\r/, "\\r")
            gsub(/\n/, "\\n")
            printf "%s", $0
        }
    '
}

severity_rank() {
    case "$1" in
        BLOCKER) echo 4 ;;
        MAJOR) echo 3 ;;
        MINOR) echo 2 ;;
        NIT) echo 1 ;;
        *) echo 0 ;;
    esac
}

max_severity() {
    current="$1"
    candidate="$2"
    if [ "$(severity_rank "$candidate")" -gt "$(severity_rank "$current")" ]; then
        echo "$candidate"
    else
        echo "$current"
    fi
}

render_gate_status() {
    case "$1" in
        BLOCKER|MAJOR)
            echo "FAIL"
            ;;
        MINOR)
            echo "PASS WITH MINORS"
            ;;
        *)
            echo "PASS"
            ;;
    esac
}

extract_md_tokens() {
    awk '
        {
            line = $0
            while (match(line, /[A-Za-z0-9_./-]+\.md([?#][A-Za-z0-9_./#-]+)?/)) {
                print substr(line, RSTART, RLENGTH)
                line = substr(line, RSTART + RLENGTH)
            }
        }
    ' "$1" 2>/dev/null | sort -u || true
}

resolve_markdown_ref() {
    ref="$1"
    base_file="$2"

    ref=${ref%%#*}
    ref=${ref%%\?*}

    case "$ref" in
        ""|http://*|https://*|mailto:*|file://*)
            return 1
            ;;
        *.md)
            ;;
        *)
            return 1
            ;;
    esac

    case "$ref" in
        /*)
            rel_from_root="${ref#/}"
            if [ -f "$SKILL_DIR/$rel_from_root" ]; then
                abs="$SKILL_DIR/$rel_from_root"
            else
                abs="$ref"
            fi
            ;;
        *)
            base_dir=$(dirname "$base_file")
            ref_dir=$(dirname "$ref")
            ref_base=$(basename "$ref")
            resolved_dir=$(cd "$base_dir" 2>/dev/null && cd "$ref_dir" 2>/dev/null && pwd -P) || return 1
            abs="$resolved_dir/$ref_base"
            ;;
    esac

    [ -f "$abs" ] || return 1

    case "$abs" in
        "$SKILL_DIR"/*)
            printf '%s\n' "${abs#"$SKILL_DIR"/}"
            ;;
        *)
            return 1
            ;;
    esac
}

SCOPE="all"
FORMAT="text"
MAX_HOPS=2
SKILL_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --scope)
            require_opt_value "--scope" "${2-}"
            shift
            SCOPE="$1"
            ;;
        --format)
            require_opt_value "--format" "${2-}"
            shift
            FORMAT="$1"
            ;;
        --max-hops)
            require_opt_value "--max-hops" "${2-}"
            shift
            MAX_HOPS="$1"
            ;;
        --*)
            echo "error: unknown option: $1"
            exit 1
            ;;
        *)
            if [ -z "$SKILL_DIR" ]; then
                SKILL_DIR="$1"
            else
                echo "error: unexpected argument: $1"
                exit 1
            fi
            ;;
    esac
    shift
done

case "$SCOPE" in
    operative|advisory|all)
        ;;
    *)
        echo "error: invalid --scope: $SCOPE (expected: operative, advisory, or all)"
        exit 1
        ;;
esac

case "$FORMAT" in
    text|json)
        ;;
    *)
        echo "error: invalid --format: $FORMAT (expected: text or json)"
        exit 1
        ;;
esac

case "$MAX_HOPS" in
    ''|*[!0-9]*)
        echo "error: invalid --max-hops: $MAX_HOPS (expected a non-negative integer)"
        exit 1
        ;;
esac

if [ -z "$SKILL_DIR" ]; then
    usage
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

SKILL_DIR=$(cd "$SKILL_DIR" && pwd -P)
DIR_NAME=$(basename "$SKILL_DIR")

tmpdir=$(mktemp -d)
cleanup() {
    rm -rf "$tmpdir"
}
trap cleanup EXIT INT TERM

all_docs="$tmpdir/all_docs.txt"
operative_refs="$tmpdir/operative_refs.txt"
visited_refs="$tmpdir/visited_refs.txt"
frontier_refs="$tmpdir/frontier_refs.txt"
next_frontier_refs="$tmpdir/next_frontier_refs.txt"
scanned_docs="$tmpdir/scanned_docs.tsv"
directive_rows="$tmpdir/directive_rows.tsv"
block_rows="$tmpdir/block_rows.tsv"
directive_findings="$tmpdir/directive_findings.tsv"
block_findings="$tmpdir/block_findings.tsv"
contradiction_findings="$tmpdir/contradiction_findings.tsv"
aggregate_notes="$tmpdir/aggregate_notes.tsv"

: > "$all_docs"
: > "$operative_refs"
: > "$visited_refs"
: > "$frontier_refs"
: > "$next_frontier_refs"
: > "$scanned_docs"
: > "$directive_rows"
: > "$block_rows"
: > "$directive_findings"
: > "$block_findings"
: > "$contradiction_findings"
: > "$aggregate_notes"

find "$SKILL_DIR" -type f -name '*.md' \
    -not -path '*/.git/*' \
    -not -path '*/target/*' \
    -not -path "$SKILL_DIR/tests/*" 2>/dev/null | sort > "$all_docs"

if [ -f "$SKILL_DIR/SKILL.md" ]; then
    printf 'SKILL.md\n' >> "$operative_refs"
    printf 'SKILL.md\n' >> "$visited_refs"
    printf 'SKILL.md\n' >> "$frontier_refs"
fi

if [ -d "$SKILL_DIR/references" ]; then
    find "$SKILL_DIR/references" -type f -name '*.md' 2>/dev/null | sort | sed "s#^$SKILL_DIR/##" >> "$operative_refs"
fi

sort -u "$operative_refs" -o "$operative_refs"

hop=1
while [ "$hop" -le "$MAX_HOPS" ] && [ -s "$frontier_refs" ]; do
    : > "$next_frontier_refs"
    while IFS= read -r relpath; do
        [ -n "$relpath" ] || continue
        abs_path="$SKILL_DIR/$relpath"
        [ -f "$abs_path" ] || continue

        extract_md_tokens "$abs_path" | while IFS= read -r token; do
            [ -n "$token" ] || continue
            resolved=$(resolve_markdown_ref "$token" "$abs_path" || true)
            [ -n "$resolved" ] || continue
            if ! grep -Fx "$resolved" "$visited_refs" >/dev/null 2>&1; then
                printf '%s\n' "$resolved" >> "$visited_refs"
                printf '%s\n' "$resolved" >> "$next_frontier_refs"
            fi
        done
    done < "$frontier_refs"

    if [ -s "$next_frontier_refs" ]; then
        sort -u "$next_frontier_refs" -o "$next_frontier_refs"
        cat "$next_frontier_refs" >> "$operative_refs"
        sort -u "$operative_refs" -o "$operative_refs"
    fi

    cat "$next_frontier_refs" > "$frontier_refs"
    hop=$((hop + 1))
done

total_docs=0
operative_docs=0
advisory_docs=0
files_scanned=0
scanned_operative=0
scanned_advisory=0

while IFS= read -r mdfile; do
    [ -n "$mdfile" ] || continue
    relpath="${mdfile#"$SKILL_DIR"/}"
    total_docs=$((total_docs + 1))

    doc_scope="advisory"
    if grep -Fx "$relpath" "$operative_refs" >/dev/null 2>&1; then
        doc_scope="operative"
        operative_docs=$((operative_docs + 1))
    else
        advisory_docs=$((advisory_docs + 1))
    fi

    case "$SCOPE" in
        operative)
            [ "$doc_scope" = "operative" ] || continue
            ;;
        advisory)
            [ "$doc_scope" = "advisory" ] || continue
            ;;
        all)
            ;;
    esac

    files_scanned=$((files_scanned + 1))
    if [ "$doc_scope" = "operative" ]; then
        scanned_operative=$((scanned_operative + 1))
    else
        scanned_advisory=$((scanned_advisory + 1))
    fi

    printf '%s\t%s\t%s\n' "$doc_scope" "$relpath" "$mdfile" >> "$scanned_docs"

    awk -v rel="$relpath" -v scope="$doc_scope" \
        -v directives_out="$directive_rows" -v blocks_out="$block_rows" '
        function trim(s) {
            sub(/^[[:space:]]+/, "", s)
            sub(/[[:space:]]+$/, "", s)
            return s
        }
        function normalize_line(src, s) {
            s = tolower(src)
            gsub(/\[[^]]+\]\([^)]*\)/, " ", s)
            gsub(/`/, "", s)
            gsub(/\*\*/, "", s)
            gsub(/__/, "", s)
            gsub(/\*/, "", s)
            gsub(/^#+[[:space:]]+/, "", s)
            gsub(/^[[:space:]]*[-*+][[:space:]]+/, "", s)
            gsub(/^[[:space:]]*[0-9]+[.)][[:space:]]+/, "", s)
            gsub(/[[:space:]]+/, " ", s)
            return trim(s)
        }
        function contradiction_key(src, t) {
            t = " " src " "
            gsub(/[[:punct:]]/, " ", t)
            gsub(/[[:space:]]+/, " ", t)
            while (gsub(/ (shall|should|must|may|will|can|then|when|if|only|always|no|not|never|without|cannot|cant) /, " ", t)) {}
            gsub(/[[:space:]]+/, " ", t)
            return trim(t)
        }
        function polarity_of(src, t) {
            t = " " src " "
            if (t ~ / (shall|should|must|may) not / || t ~ / not / || t ~ / no / || t ~ / never / || t ~ / without / || t ~ / cannot / || t ~ / cant /) {
                return "negative"
            }
            return "positive"
        }
        function flush_block(   preview, chars, tokens) {
            if (block_line_count >= 3) {
                preview = block_value
                if (length(preview) > 160) {
                    preview = substr(preview, 1, 160) "..."
                }
                chars = length(block_value)
                tokens = int((chars + 3) / 4)
                printf "%s\t%s\t%d\t%d\t%d\t%d\t%s\t%s\n",
                    block_value, rel, block_start_line, block_line_count,
                    chars, tokens, scope, preview >> blocks_out
            }
            block_value = ""
            block_line_count = 0
            block_start_line = 0
        }
        BEGIN {
            in_code = 0
            block_value = ""
            block_line_count = 0
            block_start_line = 0
        }
        {
            raw = $0
            if (raw ~ /^```/) {
                if (!in_code) {
                    flush_block()
                    in_code = 1
                } else {
                    in_code = 0
                }
                next
            }
            if (in_code) {
                next
            }

            norm = normalize_line(raw)

            if (norm ~ /(^|[^[:alpha:]])(shall|should|must|may)([^[:alpha:]]|$)/) {
                key = contradiction_key(norm)
                polarity = polarity_of(norm)
                tokens = int((length(norm) + 3) / 4)
                printf "%s\t%s\t%d\t%d\t%s\t%s\t%s\n",
                    norm, rel, NR, tokens, polarity, key, scope >> directives_out
            }

            if (norm == "") {
                flush_block()
                next
            }

            if (block_line_count == 0) {
                block_start_line = NR
                block_value = norm
                block_line_count = 1
            } else {
                block_value = block_value " || " norm
                block_line_count++
            }
        }
        END {
            flush_block()
        }
    ' "$mdfile"
done < "$all_docs"

sort -t "$(printf '\t')" -k1,1 -k2,2 -k3,3n "$directive_rows" -o "$directive_rows"
sort -t "$(printf '\t')" -k1,1 -k2,2 -k3,3n "$block_rows" -o "$block_rows"

awk -F '\t' '
    function reset_group(    key) {
        for (key in files) delete files[key]
        for (key in operative_files) delete operative_files[key]
        current = ""
        representative_tokens = 0
        occurrence_list = ""
        file_list = ""
    }
    function add_unique(arr, value) {
        arr[value] = 1
    }
    function join_occurrence(existing, value) {
        if (existing == "") return value
        return existing ", " value
    }
    function join_value(existing, value) {
        if (existing == "") return value
        return existing ", " value
    }
    function severity_for(operative_count, total_count) {
        if (operative_count >= 3) return "MAJOR"
        if (operative_count >= 2) return "MINOR"
        return "NIT"
    }
    function finalize_group(    key, total_count, operative_count, waste_tokens, finding_scope, severity) {
        if (current == "") return
        total_count = 0
        operative_count = 0
        file_list = ""
        for (key in files) {
            total_count++
            file_list = join_value(file_list, key)
        }
        for (key in operative_files) operative_count++
        if (total_count < 2) {
            reset_group()
            return
        }

        finding_scope = (operative_count >= 2 ? "operative" : "advisory")
        severity = severity_for(operative_count, total_count)
        waste_tokens = (total_count - 1) * representative_tokens
        printf "%s\t%s\t%d\t%d\t%d\t%s\t%s\t%s\n",
            severity, finding_scope, waste_tokens, operative_count, total_count,
            current, file_list, occurrence_list
        reset_group()
    }
    BEGIN {
        reset_group()
    }
    {
        if (current != "" && $1 != current) finalize_group()
        if (current == "") {
            current = $1
            representative_tokens = $4
        }
        add_unique(files, $2)
        if ($7 == "operative") add_unique(operative_files, $2)
        occurrence_list = join_occurrence(occurrence_list, $2 ":" $3)
    }
    END {
        finalize_group()
    }
' "$directive_rows" | sort -t "$(printf '\t')" -k1,1 -k6,6 > "$directive_findings"

awk -F '\t' '
    function reset_group(    key) {
        for (key in files) delete files[key]
        for (key in operative_files) delete operative_files[key]
        current = ""
        current_chars = 0
        current_tokens = 0
        current_preview = ""
    }
    function add_unique(arr, value) {
        arr[value] = 1
    }
    function join_value(existing, value) {
        if (existing == "") return value
        return existing ", " value
    }
    function severity_for(operative_count, chars_value) {
        if (operative_count >= 2 && chars_value >= 160) return "MAJOR"
        if (operative_count >= 2) return "MINOR"
        return "NIT"
    }
    function finalize_group(    key, total_count, operative_count, waste_tokens, finding_scope, severity, file_list) {
        if (current == "") return
        total_count = 0
        operative_count = 0
        file_list = ""
        for (key in files) {
            total_count++
            file_list = join_value(file_list, key)
        }
        for (key in operative_files) operative_count++
        if (total_count < 2) {
            reset_group()
            return
        }
        finding_scope = (operative_count >= 2 ? "operative" : "advisory")
        severity = severity_for(operative_count, current_chars)
        waste_tokens = (total_count - 1) * current_tokens
        printf "%s\t%s\t%d\t%d\t%d\t%d\t%s\t%s\n",
            severity, finding_scope, waste_tokens, operative_count, total_count,
            current_chars, current_preview, file_list
        reset_group()
    }
    BEGIN {
        reset_group()
    }
    {
        if (current != "" && $1 != current) finalize_group()
        if (current == "") {
            current = $1
            current_chars = $5
            current_tokens = $6
            current_preview = $8
        }
        add_unique(files, $2)
        if ($7 == "operative") add_unique(operative_files, $2)
    }
    END {
        finalize_group()
    }
' "$block_rows" | sort -t "$(printf '\t')" -k1,1 -k7,7 > "$block_findings"

awk -F '\t' '
    function reset_group(    key) {
        for (key in all_files) delete all_files[key]
        for (key in pos_files) delete pos_files[key]
        for (key in neg_files) delete neg_files[key]
        for (key in op_pos_files) delete op_pos_files[key]
        for (key in op_neg_files) delete op_neg_files[key]
        current = ""
        positive_example = ""
        negative_example = ""
    }
    function add_unique(arr, value) {
        arr[value] = 1
    }
    function join_value(existing, value) {
        if (existing == "") return value
        return existing ", " value
    }
    function finalize_group(    key, total_count, operative_total, pos_count, neg_count, op_pos_count, op_neg_count, file_list, scope_value, severity) {
        if (current == "") return
        total_count = 0
        operative_total = 0
        pos_count = 0
        neg_count = 0
        op_pos_count = 0
        op_neg_count = 0
        file_list = ""
        for (key in all_files) {
            total_count++
            file_list = join_value(file_list, key)
        }
        for (key in pos_files) pos_count++
        for (key in neg_files) neg_count++
        for (key in op_pos_files) {
            op_pos_count++
            operative_total++
        }
        for (key in op_neg_files) {
            op_neg_count++
            if (!(key in op_pos_files)) operative_total++
        }
        if (pos_count == 0 || neg_count == 0 || total_count < 2) {
            reset_group()
            return
        }
        scope_value = (op_pos_count > 0 && op_neg_count > 0 && operative_total >= 2 ? "operative" : "advisory")
        severity = (scope_value == "operative" ? "BLOCKER" : "NIT")
        printf "%s\t%s\t%d\t%d\t%s\t%s\t%s\t%s\n",
            severity, scope_value, operative_total, total_count,
            current, positive_example, negative_example, file_list
        reset_group()
    }
    BEGIN {
        reset_group()
    }
    {
        if ($6 == "") next
        if (current != "" && $6 != current) finalize_group()
        if (current == "") current = $6
        add_unique(all_files, $2)
        if ($5 == "positive") {
            add_unique(pos_files, $2)
            if (positive_example == "") positive_example = $1
            if ($7 == "operative") add_unique(op_pos_files, $2)
        } else if ($5 == "negative") {
            add_unique(neg_files, $2)
            if (negative_example == "") negative_example = $1
            if ($7 == "operative") add_unique(op_neg_files, $2)
        }
    }
    END {
        finalize_group()
    }
' "$directive_rows" | sort -t "$(printf '\t')" -k1,1 -k5,5 > "$contradiction_findings"

directive_count=$(wc -l < "$directive_findings" | tr -d ' ')
block_count=$(wc -l < "$block_findings" | tr -d ' ')
contradiction_count=$(wc -l < "$contradiction_findings" | tr -d ' ')

operative_directives=$(awk -F '\t' '$2 == "operative" { count++ } END { print count + 0 }' "$directive_findings")
operative_blocks=$(awk -F '\t' '$2 == "operative" { count++ } END { print count + 0 }' "$block_findings")
operative_contradictions=$(awk -F '\t' '$2 == "operative" { count++ } END { print count + 0 }' "$contradiction_findings")

advisory_directives=$(awk -F '\t' '$2 == "advisory" { count++ } END { print count + 0 }' "$directive_findings")
advisory_blocks=$(awk -F '\t' '$2 == "advisory" { count++ } END { print count + 0 }' "$block_findings")
advisory_contradictions=$(awk -F '\t' '$2 == "advisory" { count++ } END { print count + 0 }' "$contradiction_findings")

operative_waste_directives=$(awk -F '\t' '$2 == "operative" { sum += $3 } END { print sum + 0 }' "$directive_findings")
operative_waste_blocks=$(awk -F '\t' '$2 == "operative" { sum += $3 } END { print sum + 0 }' "$block_findings")
advisory_waste_directives=$(awk -F '\t' '$2 == "advisory" { sum += $3 } END { print sum + 0 }' "$directive_findings")
advisory_waste_blocks=$(awk -F '\t' '$2 == "advisory" { sum += $3 } END { print sum + 0 }' "$block_findings")

operative_waste=$((operative_waste_directives + operative_waste_blocks))
advisory_waste=$((advisory_waste_directives + advisory_waste_blocks))
total_waste=$((operative_waste + advisory_waste))

highest_operative="NONE"
while IFS='	' read -r severity finding_scope _rest; do
    [ -n "$severity" ] || continue
    [ "$finding_scope" = "operative" ] || continue
    highest_operative=$(max_severity "$highest_operative" "$severity")
done < "$directive_findings"

while IFS='	' read -r severity finding_scope _rest; do
    [ -n "$severity" ] || continue
    [ "$finding_scope" = "operative" ] || continue
    highest_operative=$(max_severity "$highest_operative" "$severity")
done < "$block_findings"

while IFS='	' read -r severity finding_scope _rest; do
    [ -n "$severity" ] || continue
    [ "$finding_scope" = "operative" ] || continue
    highest_operative=$(max_severity "$highest_operative" "$severity")
done < "$contradiction_findings"

aggregate_severity="NONE"
if [ "$operative_waste" -ge 200 ]; then
    aggregate_severity="MAJOR"
    highest_operative=$(max_severity "$highest_operative" "$aggregate_severity")
    printf '%s\t%s\n' "$aggregate_severity" "Cumulative operative duplicate waste is ~${operative_waste} tokens (threshold: 200)." >> "$aggregate_notes"
elif [ "$operative_waste" -ge 20 ]; then
    aggregate_severity="MINOR"
    highest_operative=$(max_severity "$highest_operative" "$aggregate_severity")
    printf '%s\t%s\n' "$aggregate_severity" "Cumulative operative duplicate waste is ~${operative_waste} tokens (threshold: 20)." >> "$aggregate_notes"
fi

highest_overall="$highest_operative"
if [ "$highest_overall" = "NONE" ]; then
    while IFS='	' read -r severity _rest; do
        [ -n "$severity" ] || continue
        highest_overall=$(max_severity "$highest_overall" "$severity")
    done < "$directive_findings"
    while IFS='	' read -r severity _rest; do
        [ -n "$severity" ] || continue
        highest_overall=$(max_severity "$highest_overall" "$severity")
    done < "$block_findings"
    while IFS='	' read -r severity _rest; do
        [ -n "$severity" ] || continue
        highest_overall=$(max_severity "$highest_overall" "$severity")
    done < "$contradiction_findings"
fi

gate_status=$(render_gate_status "$highest_operative")

print_text_section() {
    section_title="$1"
    section_file="$2"
    kind="$3"

    echo "$section_title"
    if [ ! -s "$section_file" ]; then
        echo "  ✓ None"
        echo ""
        return
    fi

    case "$kind" in
        directives)
            while IFS='	' read -r severity finding_scope waste_tokens operative_count total_count text_value files_value occurrences_value; do
                [ -n "$severity" ] || continue
                printf '  [%s | %s | HIGH [H]] %s\n' "$severity" "$finding_scope" "$text_value"
                printf '    Files: %s\n' "$files_value"
                printf '    Coverage: %s total files, %s operative files\n' "$total_count" "$operative_count"
                printf '    Occurrences: %s\n' "$occurrences_value"
                if [ "$waste_tokens" -gt 0 ]; then
                    printf '    Estimated waste: ~%s tokens\n' "$waste_tokens"
                fi
            done < "$section_file"
            ;;
        blocks)
            while IFS='	' read -r severity finding_scope waste_tokens operative_count total_count chars_value preview_value files_value; do
                [ -n "$severity" ] || continue
                printf '  [%s | %s | HIGH [H]] %s\n' "$severity" "$finding_scope" "$preview_value"
                printf '    Files: %s\n' "$files_value"
                printf '    Coverage: %s total files, %s operative files\n' "$total_count" "$operative_count"
                printf '    Normalized size: %s chars\n' "$chars_value"
                if [ "$waste_tokens" -gt 0 ]; then
                    printf '    Estimated waste: ~%s tokens\n' "$waste_tokens"
                fi
            done < "$section_file"
            ;;
        contradictions)
            while IFS='	' read -r severity finding_scope operative_count total_count key_value positive_value negative_value files_value; do
                [ -n "$severity" ] || continue
                printf '  [%s | %s | HIGH [H]] positive: %s | negative: %s\n' "$severity" "$finding_scope" "$positive_value" "$negative_value"
                printf '    Key: %s\n' "$key_value"
                printf '    Files: %s\n' "$files_value"
                printf '    Coverage: %s total files, %s operative files\n' "$total_count" "$operative_count"
            done < "$section_file"
            ;;
    esac
    echo ""
}

if [ "$FORMAT" = "text" ]; then
    printf '═══ Duplication Detection: %s ═══\n\n' "$DIR_NAME"
    echo "Scope: $SCOPE"
    echo "Format: $FORMAT"
    echo "Max hops: $MAX_HOPS"
    echo ""
    echo "── Scan Coverage ──"
    echo "  Total markdown docs: $total_docs"
    echo "  Operative docs available: $operative_docs"
    echo "  Advisory docs available: $advisory_docs"
    echo "  Docs scanned: $files_scanned"
    echo "  Operative docs scanned: $scanned_operative"
    echo "  Advisory docs scanned: $scanned_advisory"
    echo ""
    echo "── Phase 4b Gate ──"
    echo "  Status: $gate_status"
    echo "  Highest operative severity: $highest_operative"
    echo "  Operative duplicate waste: ~${operative_waste} tokens"
    echo ""

    print_text_section "── Exact Directive Duplicates ──" "$directive_findings" "directives"
    print_text_section "── Exact Instruction-Block Duplicates ──" "$block_findings" "blocks"
    print_text_section "── Contradiction Candidates ──" "$contradiction_findings" "contradictions"

    echo "── Aggregate Notes ──"
    if [ -s "$aggregate_notes" ]; then
        while IFS='	' read -r severity note; do
            printf '  [%s | operative | HIGH [H]] %s\n' "$severity" "$note"
        done < "$aggregate_notes"
    else
        echo "  ✓ None"
    fi
    echo ""
    echo "── Summary ──"
    echo "  Directive duplicate findings: $directive_count (operative: $operative_directives, advisory: $advisory_directives)"
    echo "  Block duplicate findings: $block_count (operative: $operative_blocks, advisory: $advisory_blocks)"
    echo "  Contradiction candidates: $contradiction_count (operative: $operative_contradictions, advisory: $advisory_contradictions)"
    echo "  Total estimated duplicate waste: ~${total_waste} tokens"
    echo "  Confidence: HIGH [H] (deterministic)"
    echo ""
    echo "Done."
    exit 0
fi

printf '{'
printf '"skill_dir":"%s",' "$(json_escape "$SKILL_DIR")"
printf '"scope":"%s",' "$(json_escape "$SCOPE")"
printf '"format":"json",'
printf '"max_hops":%s,' "$MAX_HOPS"
printf '"confidence":"HIGH [H]",'
printf '"summary":{'
printf '"total_markdown_docs":%s,' "$total_docs"
printf '"operative_docs_available":%s,' "$operative_docs"
printf '"advisory_docs_available":%s,' "$advisory_docs"
printf '"files_scanned":%s,' "$files_scanned"
printf '"operative_docs_scanned":%s,' "$scanned_operative"
printf '"advisory_docs_scanned":%s,' "$scanned_advisory"
printf '"directive_findings":%s,' "$directive_count"
printf '"block_findings":%s,' "$block_count"
printf '"contradiction_findings":%s,' "$contradiction_count"
printf '"operative_duplicate_waste_tokens":%s,' "$operative_waste"
printf '"advisory_duplicate_waste_tokens":%s,' "$advisory_waste"
printf '"total_duplicate_waste_tokens":%s,' "$total_waste"
printf '"highest_operative_severity":"%s",' "$(json_escape "$highest_operative")"
printf '"highest_overall_severity":"%s",' "$(json_escape "$highest_overall")"
printf '"aggregate_operative_waste_severity":"%s"' "$(json_escape "$aggregate_severity")"
printf '},'
printf '"gate":{'
printf '"status":"%s",' "$(json_escape "$gate_status")"
printf '"operative_findings_gate_verdict":%s' "$( [ "$gate_status" = "FAIL" ] && echo "false" || echo "true" )"
printf '},'

printf '"directive_duplicates":['
first=1
while IFS='	' read -r severity finding_scope waste_tokens operative_count total_count text_value files_value occurrences_value; do
    [ -n "$severity" ] || continue
    if [ "$first" -eq 0 ]; then
        printf ','
    fi
    first=0
    printf '{'
    printf '"severity":"%s",' "$(json_escape "$severity")"
    printf '"scope":"%s",' "$(json_escape "$finding_scope")"
    printf '"confidence":"HIGH [H]",'
    printf '"operative_file_count":%s,' "$operative_count"
    printf '"total_file_count":%s,' "$total_count"
    printf '"estimated_waste_tokens":%s,' "$waste_tokens"
    printf '"text":"%s",' "$(json_escape "$text_value")"
    printf '"files":"%s",' "$(json_escape "$files_value")"
    printf '"occurrences":"%s"' "$(json_escape "$occurrences_value")"
    printf '}'
done < "$directive_findings"
printf '],'

printf '"block_duplicates":['
first=1
while IFS='	' read -r severity finding_scope waste_tokens operative_count total_count chars_value preview_value files_value; do
    [ -n "$severity" ] || continue
    if [ "$first" -eq 0 ]; then
        printf ','
    fi
    first=0
    printf '{'
    printf '"severity":"%s",' "$(json_escape "$severity")"
    printf '"scope":"%s",' "$(json_escape "$finding_scope")"
    printf '"confidence":"HIGH [H]",'
    printf '"operative_file_count":%s,' "$operative_count"
    printf '"total_file_count":%s,' "$total_count"
    printf '"normalized_char_count":%s,' "$chars_value"
    printf '"estimated_waste_tokens":%s,' "$waste_tokens"
    printf '"preview":"%s",' "$(json_escape "$preview_value")"
    printf '"files":"%s"' "$(json_escape "$files_value")"
    printf '}'
done < "$block_findings"
printf '],'

printf '"contradiction_candidates":['
first=1
while IFS='	' read -r severity finding_scope operative_count total_count key_value positive_value negative_value files_value; do
    [ -n "$severity" ] || continue
    if [ "$first" -eq 0 ]; then
        printf ','
    fi
    first=0
    printf '{'
    printf '"severity":"%s",' "$(json_escape "$severity")"
    printf '"scope":"%s",' "$(json_escape "$finding_scope")"
    printf '"confidence":"HIGH [H]",'
    printf '"operative_file_count":%s,' "$operative_count"
    printf '"total_file_count":%s,' "$total_count"
    printf '"key":"%s",' "$(json_escape "$key_value")"
    printf '"positive_example":"%s",' "$(json_escape "$positive_value")"
    printf '"negative_example":"%s",' "$(json_escape "$negative_value")"
    printf '"files":"%s"' "$(json_escape "$files_value")"
    printf '}'
done < "$contradiction_findings"
printf '],'

printf '"aggregate_notes":['
first=1
while IFS='	' read -r severity note; do
    [ -n "$severity" ] || continue
    if [ "$first" -eq 0 ]; then
        printf ','
    fi
    first=0
    printf '{'
    printf '"severity":"%s",' "$(json_escape "$severity")"
    printf '"scope":"operative",'
    printf '"confidence":"HIGH [H]",'
    printf '"note":"%s"' "$(json_escape "$note")"
    printf '}'
done < "$aggregate_notes"
printf ']'
printf '}\n'
