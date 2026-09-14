#!/usr/bin/env sh

set -eu

FORMAT=text
MARKETPLACE=""
INSTALLED=""
INSTALL_UNCHECKED=0

usage() {
    cat <<'EOF'
Usage: plugin_check.sh <plugin-directory> [--marketplace <file>] [--installed <dir>] [--format json]

Report deterministic package facts no single SKILL.md can see:
  - which host manifests and bundled skills are present
  - shared-field differences between available host manifests
  - differences between a one-skill package description and skill description
  - a declared license having a LICENSE file behind it
  - catalog version parity            (needs --marketplace, else auto-discovered)
  - installed skill-tree drift        (use --installed for the observed active version;
                                        auto-discovery runs only when unambiguous)

Package shape and shared-field differences are observations, not policy
verdicts: a target may intentionally support one host, expose no skills, or
publish host-specific metadata. Each observation needs target and host
interpretation. The script fails only when its arguments or target are
unusable; it does not decide whether a plugin is good or release-ready.

Surfaces that cannot be located are reported as unchecked, never as passing.

Exit: 0 report produced, 2 the arguments or the target were unusable.
EOF
}

json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

fail_usage() {
    echo "error: $1" >&2
    [ -z "${2-}" ] || echo "hint: $2" >&2
    exit 2
}

# An observation is a fact plus, where one exists, the documented rule it bears
# on. It carries no severity: ranking these is the reader's judgment, and a
# script that ranked them would be deciding for a target it cannot see.
observe() {
    code="$1"
    subject="$2"
    fact="$3"
    source_ref="${4-}"

    if [ "$OBS_COUNT" -gt 0 ]; then
        OBS_JSON="$OBS_JSON,"
    fi
    OBS_JSON="$OBS_JSON{\"code\":\"$(json_escape "$code")\",\"subject\":\"$(json_escape "$subject")\",\"fact\":\"$(json_escape "$fact")\""
    if [ -n "$source_ref" ]; then
        OBS_JSON="$OBS_JSON,\"source\":\"$(json_escape "$source_ref")\""
    fi
    OBS_JSON="$OBS_JSON}"
    OBS_COUNT=$((OBS_COUNT + 1))

    TEXT_OBS="$TEXT_OBS
$code: $subject
  $fact"
    if [ -n "$source_ref" ]; then
        TEXT_OBS="$TEXT_OBS
  source: $source_ref"
    fi
}

append_unchecked() {
    what="$1"
    if [ -n "$UNCHECKED" ]; then UNCHECKED="$UNCHECKED,$what"; else UNCHECKED="$what"; fi
}

# Top-level JSON string field. Manifest values are single-line by JSON rules.
json_field() {
    field="$1"; file="$2"
    grep -oE "\"$field\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" "$file" 2>/dev/null |
        head -1 | sed -e "s/^\"$field\"[[:space:]]*:[[:space:]]*\"//" -e 's/"$//' || true
}

# Fold a YAML frontmatter block scalar into one line.
yaml_description() {
    awk '
        NR == 1 && $0 == "---" { in_fm = 1; next }
        in_fm && $0 == "---" { exit }
        !in_fm { next }
        /^description:/ {
            collecting = 1
            rest = $0
            sub(/^description:[[:space:]]*/, "", rest)
            if (rest != "" && rest !~ /^[>|][-+]?$/) { printf "%s", rest }
            next
        }
        collecting && /^[A-Za-z_-]+:/ { collecting = 0 }
        collecting {
            line = $0
            sub(/^[[:space:]]+/, "", line)
            if (line != "") { printf "%s ", line }
        }
    ' "$1" | sed -e 's/[[:space:]]\{1,\}/ /g' -e 's/^ //' -e 's/ $//'
}

# One cheap scan of the small slug/description lookup, not a re-parse of a
# SKILL.md file. Populated once, below, before any caller needs it.
desc_for_slug() {
    awk -F'\t' -v s="$1" '$1 == s { sub(/^[^\t]*\t/, ""); print; exit }' "$DESC_LOOKUP"
}

# Compare descriptions on content, not encoding. JSON escapes non-ASCII as
# \uXXXX while YAML carries the literal bytes, so an em-dash alone would report
# every such description as drifted. Fold both forms to one placeholder.
normalize() {
    printf '%s' "$1" |
        sed -e 's/\\u[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]/?/g' |
        tr -c '\11\12\40-\176' '?' |
        tr -s '?' |
        sed -e 's/[[:space:]]\{1,\}/ /g' -e 's/^ //' -e 's/ $//'
}

print_text() {
    echo "REPORT plugin_check"
    echo "plugin_dir=$PLUGIN_DIR"
    echo "plugin=$PLUGIN_NAME"
    echo "skills=$SKILL_COUNT"
    if [ -n "$UNCHECKED" ]; then echo "unchecked=$UNCHECKED"; fi
    echo "errors=$ERR_COUNT"
    echo "observations=$OBS_COUNT"
    [ "$OBS_COUNT" -eq 0 ] || printf '%s\n' "$TEXT_OBS"
    exit 0
}

print_json() {
    printf '{'
    printf '"script":"plugin_check",'
    printf '"plugin_dir":"%s",' "$(json_escape "$PLUGIN_DIR")"
    printf '"plugin":"%s",' "$(json_escape "$PLUGIN_NAME")"
    printf '"skills":%s,' "$SKILL_COUNT"
    printf '"unchecked":"%s",' "$(json_escape "$UNCHECKED")"
    printf '"error_count":%s,' "$ERR_COUNT"
    printf '"errors":[%s],' "$ERR_JSON"
    printf '"observation_count":%s,' "$OBS_COUNT"
    printf '"observations":[%s]' "$OBS_JSON"
    printf '}\n'
    exit 0
}

ERR_JSON=""
ERR_COUNT=0
TEXT_OBS=""
OBS_JSON=""
OBS_COUNT=0
SKILL_COUNT=0
UNCHECKED=""
PLUGIN_NAME=""
PLUGIN_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --format) FORMAT="${2-}"; shift 2 ;;
        --format=*) FORMAT=${1#*=}; shift ;;
        --marketplace) MARKETPLACE="${2-}"; shift 2 ;;
        --marketplace=*) MARKETPLACE=${1#*=}; shift ;;
        --installed) INSTALLED="${2-}"; shift 2 ;;
        --installed=*) INSTALLED=${1#*=}; shift ;;
        -*) fail_usage "unknown flag: $1" ;;
        *)
            [ -z "$PLUGIN_DIR" ] || fail_usage "only one plugin directory may be provided"
            PLUGIN_DIR="$1"; shift ;;
    esac
done

[ -n "$PLUGIN_DIR" ] || { usage >&2; exit 2; }

case "$FORMAT" in
    text|json) ;;
    *) fail_usage "unsupported format: $FORMAT" "use text or json" ;;
esac

# Not a finding about the target: the script could not run.
[ -d "$PLUGIN_DIR" ] || fail_usage "plugin directory not found: $PLUGIN_DIR"

PLUGIN_NAME=$(basename "$PLUGIN_DIR")
CLAUDE_MANIFEST="$PLUGIN_DIR/.claude-plugin/plugin.json"
CODEX_MANIFEST="$PLUGIN_DIR/.codex-plugin/plugin.json"

# --- manifests present -----------------------------------------------------

CLAUDE_VERSION=""; CLAUDE_DESC=""; CLAUDE_LICENSE=""
CODEX_VERSION=""; CODEX_DESC=""; CODEX_LICENSE=""

if [ -f "$CLAUDE_MANIFEST" ]; then
    CLAUDE_VERSION=$(json_field version "$CLAUDE_MANIFEST")
    CLAUDE_DESC=$(json_field description "$CLAUDE_MANIFEST")
    CLAUDE_LICENSE=$(json_field license "$CLAUDE_MANIFEST")
else
    observe "missing_claude_manifest" ".claude-plugin/plugin.json" \
        "the file does not exist; this package exposes no Claude manifest at that path" \
        "plugin-fit"
    append_unchecked "claude-manifest-fields"
fi

if [ -f "$CODEX_MANIFEST" ]; then
    CODEX_VERSION=$(json_field version "$CODEX_MANIFEST")
    CODEX_DESC=$(json_field description "$CODEX_MANIFEST")
    CODEX_LICENSE=$(json_field license "$CODEX_MANIFEST")
else
    observe "missing_codex_manifest" ".codex-plugin/plugin.json" \
        "the file does not exist; this package exposes no Codex manifest at that path" \
        "plugin-fit"
    append_unchecked "codex-manifest-fields"
fi

if [ -n "$CLAUDE_VERSION" ] && [ -n "$CODEX_VERSION" ] && [ "$CLAUDE_VERSION" != "$CODEX_VERSION" ]; then
    observe "manifest_version_difference" "version" \
        "claude manifest says $CLAUDE_VERSION, codex manifest says $CODEX_VERSION" \
        "plugin-fit"
fi

if [ -n "$CLAUDE_DESC" ] && [ -n "$CODEX_DESC" ]; then
    if [ "$(normalize "$CLAUDE_DESC")" != "$(normalize "$CODEX_DESC")" ]; then
        observe "manifest_description_difference" "description" \
            "claude and codex manifests expose different description text" \
            "plugin-fit"
    fi
fi

if [ -n "$CLAUDE_LICENSE" ] && [ -n "$CODEX_LICENSE" ] && [ "$CLAUDE_LICENSE" != "$CODEX_LICENSE" ]; then
    observe "manifest_license_difference" "license" \
        "claude manifest says $CLAUDE_LICENSE, codex manifest says $CODEX_LICENSE" \
        "plugin-fit"
fi

# --- bundled skills --------------------------------------------------------

SKILL_FILES=""
if [ -d "$PLUGIN_DIR/skills" ]; then
    SKILL_FILES=$(find "$PLUGIN_DIR/skills" -mindepth 2 -maxdepth 2 -name 'SKILL.md' | sort)
fi

if [ -n "$SKILL_FILES" ]; then
    SKILL_COUNT=$(printf '%s\n' "$SKILL_FILES" | sed '/^$/d' | wc -l | tr -d ' ')
fi

if [ "$SKILL_COUNT" -eq 0 ]; then
    observe "no_skills" "skills" "no SKILL.md was found under the package skills directory" \
        "plugin-fit"
fi

# Fold every bundled skill's description once. The single-skill manifest
# comparison and installed-drift check can then reuse the same parsed facts.
SCRATCH_DIR=$(mktemp -d "${TMPDIR:-/tmp}/plugincheck.XXXXXXXXXX") || fail_usage "cannot create private scratch directory"
trap 'rm -rf -- "$SCRATCH_DIR"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
DESC_LOOKUP="$SCRATCH_DIR/descriptions"
: >"$DESC_LOOKUP"

while IFS= read -r sf; do
    [ -n "$sf" ] || continue
    slug=$(basename "$(dirname "$sf")")
    printf '%s\t%s\n' "$slug" "$(yaml_description "$sf")" >>"$DESC_LOOKUP"
done <<EOF
$SKILL_FILES
EOF

if [ "$SKILL_COUNT" -eq 1 ]; then
    only_skill=$(printf '%s\n' "$SKILL_FILES" | head -1)
    only_slug=$(basename "$(dirname "$only_skill")")
    skill_desc=$(desc_for_slug "$only_slug")
    if [ -n "$skill_desc" ] && [ -n "$CLAUDE_DESC" ]; then
        if [ "$(normalize "$skill_desc")" != "$(normalize "$CLAUDE_DESC")" ]; then
            observe "skill_description_difference" "$only_slug" \
                "the Claude package description differs from this skill's frontmatter description" \
                "plugin-fit"
        fi
    fi
    if [ -n "$skill_desc" ] && [ -n "$CODEX_DESC" ]; then
        if [ "$(normalize "$skill_desc")" != "$(normalize "$CODEX_DESC")" ]; then
            observe "skill_description_difference" "$only_slug" \
                "the Codex package description differs from this skill's frontmatter description" \
                "plugin-fit"
        fi
    fi
fi

# Declared capability versus actual use is deliberately not checked here. Every
# plugin in this repository declares Read or Read+Write while several invoke
# scripts, so a check would flag the whole set against a convention that may be
# correct; whether the host schema even defines an execute capability is unknown.
# Plugin fit keeps it as a judgment item instead.

# --- license ---------------------------------------------------------------

DECLARED_LICENSE="$CLAUDE_LICENSE"
[ -n "$DECLARED_LICENSE" ] || DECLARED_LICENSE="$CODEX_LICENSE"
if [ -n "$DECLARED_LICENSE" ]; then
    license_found=no
    probe="$PLUGIN_DIR"
    depth=0
    while [ "$depth" -lt 5 ]; do
        for candidate in LICENSE LICENSE.md LICENSE.txt COPYING; do
            if [ -f "$probe/$candidate" ]; then license_found=yes; fi
        done
        [ "$license_found" = no ] || break
        probe=$(dirname "$probe")
        [ "$probe" != "/" ] || break
        depth=$((depth + 1))
    done
    if [ "$license_found" = no ]; then
        observe "license_without_file" "$DECLARED_LICENSE" \
            "the manifest declares this license but no LICENSE file was found above the plugin" \
            "repo-overlay"
    fi
fi

# --- catalog parity --------------------------------------------------------

if [ -z "$MARKETPLACE" ]; then
    probe="$PLUGIN_DIR"; depth=0
    while [ "$depth" -lt 5 ]; do
        probe=$(dirname "$probe")
        [ "$probe" != "/" ] || break
        if [ -f "$probe/.claude-plugin/marketplace.json" ]; then
            MARKETPLACE="$probe/.claude-plugin/marketplace.json"
            break
        fi
        depth=$((depth + 1))
    done
fi

if [ -n "$MARKETPLACE" ] && [ -f "$MARKETPLACE" ]; then
    # Scan forward from the plugin's name to its version, stopping at the next
    # entry. Splitting the file on commas would break inside any description
    # that contains one, silently pushing version out of reach.
    catalog_version=$(awk -v target="$PLUGIN_NAME" '
        index($0, "\"name\"") && index($0, "\"" target "\"") { found = 1; next }
        found && index($0, "\"name\"") { exit }
        found && index($0, "\"version\"") {
            line = $0
            sub(/.*"version"[[:space:]]*:[[:space:]]*"/, "", line)
            sub(/".*/, "", line)
            print line
            exit
        }
    ' "$MARKETPLACE")

    if ! grep -q "\"$PLUGIN_NAME\"" "$MARKETPLACE" 2>/dev/null; then
        observe "not_published" "$PLUGIN_NAME" "no entry in $MARKETPLACE" "repo-overlay"
    else
        # Tracking is a useful fact, but a local or generated catalog can
        # intentionally point at untracked content. The agent judges whether
        # that contradicts the package's publication claim.
        if command -v git >/dev/null 2>&1 &&
           git -C "$PLUGIN_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            if [ -z "$(git -C "$PLUGIN_DIR" ls-files . 2>/dev/null | head -1)" ]; then
                observe "published_but_untracked" "$PLUGIN_NAME" \
                    "the catalog entry exists but no file under the plugin directory is tracked by git" \
                    "repo-overlay"
            fi
        else
            append_unchecked "tracking"
        fi
    fi

    if grep -q "\"$PLUGIN_NAME\"" "$MARKETPLACE" 2>/dev/null; then
        if [ -z "$catalog_version" ]; then
            observe "catalog_no_version" "$PLUGIN_NAME" \
                "catalog entry declares no version to compare against" \
                "repo-overlay"
        elif [ -n "$CLAUDE_VERSION" ] && [ "$catalog_version" != "$CLAUDE_VERSION" ]; then
            observe "catalog_version_difference" "version" \
                "catalog says $catalog_version, Claude manifest says $CLAUDE_VERSION" \
                "repo-overlay"
        fi
    fi
else
    append_unchecked "catalog"
fi

# --- installed skill-tree drift -------------------------------------------

# Emit a deterministic description of the skill subtree. Content, topology,
# and whether regular files are executable are facts the installed runtime can
# observe. Host package surfaces outside the skill tree remain explicitly
# unchecked rather than being inferred from matching frontmatter.
tree_facts() {
    base="$1"
    find "$base" -mindepth 1 -print 2>/dev/null | LC_ALL=C sort | while IFS= read -r item; do
        rel=${item#"$base"/}
        if [ -d "$item" ] && [ ! -L "$item" ]; then
            printf 'D\t%s\n' "$rel"
        elif [ -f "$item" ] && [ ! -L "$item" ]; then
            if [ -x "$item" ]; then executable=x; else executable=-; fi
            set -- $(cksum "$item")
            printf 'F\t%s\t%s\t%s\t%s\n' "$rel" "$executable" "$1" "$2"
        elif [ -L "$item" ]; then
            printf 'L\t%s\n' "$rel"
        else
            printf 'O\t%s\n' "$rel"
        fi
    done
}

if [ -z "$INSTALLED" ]; then
    installed_candidates=""
    for base in "$HOME/.claude/plugins/cache" "$HOME/.codex/plugins/cache"; do
        [ -d "$base" ] || continue
        found=$(find "$base" -mindepth 2 -maxdepth 3 -type d -name "$PLUGIN_NAME" 2>/dev/null || true)
        [ -z "$found" ] || installed_candidates="$installed_candidates
$found"
    done
    installed_candidates=$(printf '%s\n' "$installed_candidates" | sed '/^$/d' | sort -u)
    candidate_count=$(printf '%s\n' "$installed_candidates" | sed '/^$/d' | wc -l | tr -d ' ')
    if [ "$candidate_count" -eq 1 ]; then
        INSTALLED="$installed_candidates"
    elif [ "$candidate_count" -gt 1 ]; then
        append_unchecked "install-multiple-host-caches-use---installed"
        INSTALL_UNCHECKED=1
    fi
fi

if [ -n "$INSTALLED" ] && [ -d "$INSTALLED" ]; then
    while IFS= read -r sf; do
        [ -n "$sf" ] || continue
        slug=$(basename "$(dirname "$sf")")
        installed_skills=$(find "$INSTALLED" -type f -path "*/$slug/SKILL.md" 2>/dev/null | sort -u || true)
        installed_count=$(printf '%s\n' "$installed_skills" | sed '/^$/d' | wc -l | tr -d ' ')
        if [ "$installed_count" -gt 1 ]; then
            append_unchecked "install-$slug-multiple-copies-use---installed"
            continue
        fi
        if [ "$installed_count" -eq 1 ]; then
            installed_skill="$installed_skills"
            repo_skill_dir=$(dirname "$sf")
            installed_skill_dir=$(dirname "$installed_skill")
            repo_tree="$SCRATCH_DIR/repo-tree"
            installed_tree="$SCRATCH_DIR/installed-tree"
            tree_facts "$repo_skill_dir" >"$repo_tree"
            tree_facts "$installed_skill_dir" >"$installed_tree"
            if ! cmp -s "$repo_tree" "$installed_tree"; then
                observe "install_drift" "$slug" \
                    "the installed skill tree differs from the repository in content, topology, or executable-file availability" \
                    "plugin-fit"
            fi
            rm -f "$repo_tree" "$installed_tree"
        else
            append_unchecked "install-$slug-not-found"
        fi
    done <<EOF
$SKILL_FILES
EOF
    append_unchecked "install-package-surfaces-outside-skills"
else
    [ "$INSTALL_UNCHECKED" -eq 1 ] || append_unchecked "install"
fi

case "$FORMAT" in
    json) print_json ;;
    text) print_text ;;
esac
