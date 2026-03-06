#!/usr/bin/env sh
# Shared frontmatter parsing helpers for skill-auditor scripts.

sa_load_frontmatter() {
    skill_file="$1"
    first_line=$(head -1 "$skill_file")
    if [ "$first_line" != "---" ]; then
        return 1
    fi

    closing_line=$(awk 'NR > 1 && $0 == "---" { print NR; exit }' "$skill_file")
    [ -n "$closing_line" ] || return 1
    fm_block=$(sed -n "2,$((closing_line - 1))p" "$skill_file")
    [ -n "$fm_block" ] || return 1
    printf '%s\n' "$fm_block"
}

sa_frontmatter_extract_description() {
    fm_block="$1"
    desc_line=$(printf '%s\n' "$fm_block" | grep -n '^description:' | head -1)
    [ -n "$desc_line" ] || return 1

    desc_start=$(printf '%s' "$desc_line" | cut -d: -f1)
    desc_raw=$(printf '%s\n' "$fm_block" | sed -n "${desc_start}p" | sed 's/^description:[[:space:]]*//')
    case "$desc_raw" in
        ">-"|">"|"|"|"|-")
            desc_text=$(printf '%s\n' "$fm_block" | tail -n +"$((desc_start + 1))" | \
                while IFS= read -r cline; do
                    case "$cline" in
                        "  "*|"	"*) printf '%s ' "$(printf '%s' "$cline" | sed 's/^[[:space:]]*//')" ;;
                        *) break ;;
                    esac
                done)
            ;;
        *)
            desc_text="$desc_raw"
            ;;
    esac
    desc_text=$(printf '%s' "$desc_text" | sed "s/^['\"]//;s/['\"]$//")
    printf '%s' "$desc_text"
}
