# Manual Verification Commands

WHEN `scripts/verify.sh` is unavailable THEN you SHALL run these commands from the workspace root.
You SHALL paste the output of all commands as evidence.
IF any check fails THEN you SHALL fix the issue and re-run.

---

## 0. Installation checks

Before running pattern scans, you SHALL confirm the skill's artifacts are installed.

```bash
# banned_family.rs test harness
found_banned=$(find . -name 'banned_family.rs' -path '*/tests/*' -not -path '*/target/*' -print -quit)
if [ -n "$found_banned" ]; then
  if grep -qF '("assert_eq", MatchKind::MacroOnly),' "$found_banned" \
    && grep -qF '("assert_ne", MatchKind::MacroOnly),' "$found_banned" \
    && grep -qF '("assert", MatchKind::MacroOnly),' "$found_banned"; then
    echo "ok: banned_family.rs installed with assert coverage: $found_banned"
  else
    echo "WARN: banned_family.rs lacks assert coverage (re-run scaffold.sh --banned-test): $found_banned"
  fi
else
  echo "WARN: banned_family.rs not found (run scaffold.sh --banned-test)"
fi

# CI workflow + verifier stack
git_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ -f ".github/workflows/ci.yml" ] || { [ -n "$git_root" ] && [ -f "$git_root/.github/workflows/ci.yml" ]; }; then echo "ok: CI workflow installed"; else echo "WARN: CI workflow not found (run scaffold.sh --ci)"; fi
if [ -f ".github/scripts/detect_rust_workspaces.py" ] || { [ -n "$git_root" ] && [ -f "$git_root/.github/scripts/detect_rust_workspaces.py" ]; }; then echo "ok: CI detector script installed"; else echo "WARN: CI detector script not found (run scaffold.sh --ci)"; fi
if [ -f ".github/scripts/verify.sh" ] || { [ -n "$git_root" ] && [ -f "$git_root/.github/scripts/verify.sh" ]; }; then echo "ok: CI verify script installed"; else echo "WARN: CI verify script not found (run scaffold.sh --ci)"; fi
if [ -f ".github/scripts/workspace-members.sh" ] || { [ -n "$git_root" ] && [ -f "$git_root/.github/scripts/workspace-members.sh" ]; }; then echo "ok: CI workspace helper installed"; else echo "WARN: CI workspace helper not found (run scaffold.sh --ci)"; fi

# Clippy lint config
if grep -qE '^\[workspace\.lints|^\[lints' Cargo.toml 2>/dev/null; then echo "ok: clippy lint config present"; else echo "WARN: no [workspace.lints] or [lints] in Cargo.toml (run scaffold.sh --clippy)"; fi

# [lints] workspace = true in member crates (workspace only)
if grep -qF '[workspace]' Cargo.toml 2>/dev/null; then
  members=""
  members_resolved=0
  if command -v cargo >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    metadata_json=$(mktemp "${TMPDIR:-/tmp}/rust-verify-manual-metadata.XXXXXX")
    if cargo metadata --format-version 1 --no-deps --manifest-path Cargo.toml >"$metadata_json" 2>/dev/null; then
      members="$(python3 - "$metadata_json" <<'PY'
import json
import sys
from pathlib import Path

root_manifest = Path("Cargo.toml").resolve()
workspace_root = root_manifest.parent

try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except OSError as exc:
    print(f"WARN: failed to read metadata file {sys.argv[1]}: {exc}", file=sys.stderr)
    raise SystemExit(1)
except json.JSONDecodeError as exc:
    print(f"WARN: failed to parse metadata JSON {sys.argv[1]}: {exc}", file=sys.stderr)
    raise SystemExit(1)

workspace_members = payload.get("workspace_members")
packages = payload.get("packages")
if not isinstance(workspace_members, list) or not isinstance(packages, list):
    print("WARN: metadata JSON missing workspace_members/packages arrays", file=sys.stderr)
    raise SystemExit(1)

member_ids = {value for value in workspace_members if isinstance(value, str)}
paths = set()
for pkg in packages:
    if not isinstance(pkg, dict):
        continue
    if pkg.get("id") not in member_ids:
        continue
    manifest_path = pkg.get("manifest_path")
    if not isinstance(manifest_path, str):
        continue
    candidate = Path(manifest_path).resolve()
    if candidate == root_manifest:
        continue
    try:
        candidate.relative_to(workspace_root)
    except ValueError:
        continue
    paths.add(str(candidate))

for manifest_path in sorted(paths):
    print(manifest_path)
PY
)"
      members_resolved=1
    fi
    rm -f -- "$metadata_json"
  fi

  if [ "$members_resolved" -eq 0 ]; then
    echo "WARN: unable to resolve workspace members for lint inheritance check"
  elif [ -z "$members" ]; then
    echo "ok: workspace has no member crates requiring lint inheritance"
  else
    missing=$(printf '%s\n' "$members" | while IFS= read -r m; do
      [ -n "$m" ] || continue
      [ "$m" = "$(pwd)/Cargo.toml" ] && continue
      if grep -qF '[package]' "$m" 2>/dev/null; then
        if ! awk '
          BEGIN { in_lints = 0; ok = 0 }
          /^\[lints\]/ { in_lints = 1; next }
          /^\[/ { in_lints = 0 }
          in_lints && /^[[:space:]]*workspace[[:space:]]*=[[:space:]]*true([[:space:]]*(#.*)?)?$/ { ok = 1 }
          END { exit ok ? 0 : 1 }
        ' "$m" 2>/dev/null; then
          printf ' %s' "$m"
        fi
      fi
    done)
    if [ -z "$missing" ]; then echo "ok: all member crates inherit workspace lints"; else echo "WARN: missing [lints] workspace = true:$missing"; fi
  fi
fi
```

IF any installation check warns THEN you SHALL run `scaffold.sh --all` before proceeding.

---

## 1. Banned pattern scan

`// INVARIANT:` exemptions apply only when the comment appears on the same line as the banned call.
Install `python3` before running the inline-test-sensitive parser-aware subset if you want full banned-family verification coverage. Without `python3`, those checks should be reported as skipped/unverified rather than approximated with brittle regex fallbacks.

```bash
set -- \
  -g '!**/test/**' \
  -g '!**/tests/**' \
  -g '!**/testdata/**' \
  -g '!**/bench/**' \
  -g '!**/benches/**' \
  -g '!**/example/**' \
  -g '!**/examples/**' \
  -g '!**/fixture/**' \
  -g '!**/fixtures/**' \
  -g '!**/*_test.rs' \
  -g '!**/tests.rs'

# Panic-inducing patterns (excluding tests)
parser_aware_banned_scan() {
  _pattern="$1"
  _exclude_pattern="$2"
  _pass_msg="$3"
  _fail_msg="$4"

  if ! command -v python3 >/dev/null 2>&1; then
    echo "WARN: ${_pass_msg#✓ } skipped: python3 not installed; parser-aware scan unavailable"
    return 0
  fi

  _candidates_file="$(mktemp "${TMPDIR:-/tmp}/rust-verify-manual-candidates.XXXXXX")"
  if command -v rg >/dev/null 2>&1; then
    rg --files --hidden -0 -g '*.rs' >"$_candidates_file"
  elif command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files -z --cached --others --exclude-standard -- '*.rs' ':(glob)**/*.rs' >"$_candidates_file"
  else
    find . -name '*.rs' -not -path '*/target/*' -print0 >"$_candidates_file"
  fi

  if VERIFY_PATTERN="$_pattern" VERIFY_EXCLUDE_PATTERN="$_exclude_pattern" VERIFY_CANDIDATES_FILE="$_candidates_file" python3 - <<'PY'
from pathlib import Path
import os
import re
import sys

SKIP_DIRS = {"target", "test", "tests", "testdata", "bench", "benches", "example", "examples", "fixture", "fixtures"}
TEST_MODULE_PREFIXES = ("mod tests", "pub mod tests", "pub(crate) mod tests")

pattern = os.environ["VERIFY_PATTERN"]
pattern = pattern.replace("[^[:alnum:]_#]", "[^A-Za-z0-9_#]")
pattern = pattern.replace("[^[:alnum:]_]", "[^A-Za-z0-9_]")
pattern = pattern.replace("[[:alnum:]_]", "[A-Za-z0-9_]")
pattern = pattern.replace("[[:space:]]", r"\s")
TOKEN = re.compile(pattern)

exclude_pattern = os.environ.get("VERIFY_EXCLUDE_PATTERN", "")
EXCLUDE = re.compile(exclude_pattern) if exclude_pattern else None
violations = []
candidates_file = os.environ["VERIFY_CANDIDATES_FILE"]

def should_skip(path):
    if path.name == "tests.rs" or path.name.endswith("_test.rs"):
        return True
    return any(part in SKIP_DIRS for part in path.parts)

def load_candidate_paths(filename):
    payload = Path(filename).read_bytes()
    seen = set()
    paths = []
    for raw_path in payload.split(b"\0"):
        if not raw_path:
            continue
        decoded = raw_path.decode("utf-8", errors="surrogateescape")
        if decoded in seen:
            continue
        seen.add(decoded)
        path = Path(decoded)
        if not path.is_file():
            continue
        paths.append(path)
    return sorted(paths)

def strip_comments_and_strings(source: str) -> str:
    out = []
    i = 0
    block_depth = 0
    in_line_comment = False
    in_string = False
    in_char = False
    raw_hashes = None

    def is_lifetime_start(idx: int) -> bool:
        if idx + 1 >= len(source):
            return False
        next_ch = source[idx + 1]
        if not (next_ch.isalpha() or next_ch == "_"):
            return False
        j = idx + 2
        while j < len(source) and (source[j].isalnum() or source[j] == "_"):
            j += 1
        return not (j < len(source) and source[j] == "'")

    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else "\0"

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if block_depth:
            if ch == "/" and nxt == "*":
                block_depth += 1
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_depth -= 1
                i += 2
                continue
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if raw_hashes is not None:
            if ch == '"':
                if raw_hashes == 0:
                    raw_hashes = None
                else:
                    matched = 0
                    j = i + 1
                    while matched < raw_hashes and j < len(source) and source[j] == "#":
                        matched += 1
                        j += 1
                    if matched == raw_hashes:
                        raw_hashes = None
                        i = j
                        continue
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if in_char:
            if ch == "\\":
                i += 2
                continue
            if ch == "\n":
                in_char = False
                out.append(ch)
                i += 1
                continue
            if ch == "'":
                in_char = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_depth = 1
            i += 2
            continue
        if ch in {"r", "b"}:
            j = i + 1
            if ch == "b":
                if j >= len(source) or source[j] != "r":
                    out.append(ch)
                    i += 1
                    continue
                j += 1
            while j < len(source) and source[j] == "#":
                j += 1
            if j < len(source) and source[j] == '"':
                raw_hashes = j - (i + 1 if ch == "r" else i + 2)
                i = j + 1
                continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            if is_lifetime_start(i):
                out.append(ch)
                i += 1
                continue
            in_char = True
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)

def parse_cfg_test_attribute_at(lines, start_idx):
    idx = start_idx
    remainder = lines[start_idx].strip()
    while True:
        parsed = parse_outer_attribute_at(lines, idx, remainder)
        if parsed is None:
            return None
        attr, attr_end_idx, trailing = parsed
        attr_name = attr.split("(", 1)[0].strip()
        if attr_name == "cfg":
            if "(" not in attr:
                return None
            expr = attr.split("(", 1)[1].rstrip().rstrip(")").strip()
            return (expr, attr_end_idx, trailing)
        remainder = trailing.lstrip()
        if not remainder.startswith("#["):
            return None
        idx = attr_end_idx

def has_non_negated_test_token(expr):
    compact = "".join(ch for ch in expr if not ch.isspace())
    idx = 0
    in_string = False
    stack = []
    while idx < len(compact):
        ch = compact[idx]
        if in_string:
            if ch == "\\" and idx + 1 < len(compact):
                idx += 2
                continue
            if ch == '"':
                in_string = False
            idx += 1
            continue
        if ch == '"':
            in_string = True
            idx += 1
            continue
        if ch.isalnum() or ch == "_":
            start = idx
            idx += 1
            while idx < len(compact) and (compact[idx].isalnum() or compact[idx] == "_"):
                idx += 1
            ident = compact[start:idx]
            if idx < len(compact) and compact[idx] == "(":
                stack.append((ident == "not", ident == "any"))
                idx += 1
                continue
            if ident == "test":
                negated = any(is_not for is_not, _ in stack)
                inside_any = any(is_any for _, is_any in stack)
                if not negated and not inside_any:
                    return True
            continue
        if ch == "(":
            stack.append((False, False))
        elif ch == ")" and stack:
            stack.pop()
        idx += 1
    return False

def find_top_level_attr_closing_bracket(segment):
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    in_string = False
    in_char = False
    escaped = False
    raw_hashes = None
    idx = 0
    while idx < len(segment):
        ch = segment[idx]
        if raw_hashes is not None:
            if ch == '"':
                matched = 0
                j = idx + 1
                while matched < raw_hashes and j < len(segment) and segment[j] == "#":
                    matched += 1
                    j += 1
                if matched == raw_hashes:
                    raw_hashes = None
                    idx = j
                    continue
            idx += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            idx += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            idx += 1
            continue
        if ch in {"r", "b"}:
            j = idx + 1
            if ch == "b":
                if j >= len(segment) or segment[j] != "r":
                    idx += 1
                    continue
                j += 1
            while j < len(segment) and segment[j] == "#":
                j += 1
            if j < len(segment) and segment[j] == '"':
                raw_hashes = j - (idx + 1 if ch == "r" else idx + 2)
                idx = j + 1
                continue
        elif ch == '"':
            in_string = True
        elif ch == "'":
            in_char = True
        elif ch == "(":
            paren_depth += 1
        elif ch == ")" and paren_depth > 0:
            paren_depth -= 1
        elif ch == "[":
            bracket_depth += 1
        elif ch == "]":
            if paren_depth == 0 and brace_depth == 0 and bracket_depth == 0:
                return idx
            if bracket_depth > 0:
                bracket_depth -= 1
        elif ch == "{":
            brace_depth += 1
        elif ch == "}" and brace_depth > 0:
            brace_depth -= 1
        idx += 1
    return None

def parse_test_item_attribute_at(lines, start_idx):
    idx = start_idx
    remainder = lines[start_idx].strip()
    while True:
        parsed = parse_outer_attribute_at(lines, idx, remainder)
        if parsed is None:
            return None
        attr, attr_end_idx, trailing = parsed
        if not attr:
            return None
        attr_name = attr.split("(", 1)[0].strip()
        terminal = attr_name.rsplit("::", 1)[-1]
        if terminal == "test":
            return (attr, attr_end_idx, trailing)
        remainder = trailing.lstrip()
        if not remainder.startswith("#["):
            return None
        idx = attr_end_idx

def parse_outer_attribute_at(lines, start_idx, initial_remainder):
    if not initial_remainder.startswith("#["):
        return None
    remainder = initial_remainder[2:]
    attr_parts = []
    idx = start_idx
    while True:
        end_idx = find_top_level_attr_closing_bracket(remainder)
        if end_idx is not None:
            before_end = remainder[:end_idx].strip()
            if before_end:
                attr_parts.append(before_end)
            trailing = remainder[end_idx + 1:].lstrip()
            return (" ".join(attr_parts), idx, trailing)
        chunk = remainder.strip()
        if chunk:
            attr_parts.append(chunk)
        idx += 1
        if idx >= len(lines):
            return None
        remainder = lines[idx].strip()

def is_tests_module_decl(line):
    trimmed = line.lstrip()
    for prefix in TEST_MODULE_PREFIXES:
        if trimmed.startswith(prefix):
            remainder = trimmed[len(prefix):]
            if not remainder or remainder[0] in "{;" or remainder[0].isspace():
                return True
    return False

def brace_delta(line):
    return line.count("{") - line.count("}")

def cfg_annotated_item_state(line):
    if "{" in line:
        delta = brace_delta(line)
        if delta > 0:
            return ("block", delta)
        return ("complete", 0)
    if ";" in line:
        return ("complete", 0)
    return ("pending", 0)

def cfg_attr_state_from_trailing(trailing):
    trimmed = trailing.strip()
    if not trimmed:
        return ("pending", 0)
    return cfg_annotated_item_state(trimmed)

def attribute_stack_start(lines, idx):
    start = idx
    while start > 0 and lines[start - 1].strip().startswith("#["):
        start -= 1
    return start

def compute_test_line_mask(lines, sanitized_lines):
    mask = [False] * len(lines)
    pending_test_item = False
    in_test_item_block = False
    test_item_depth = 0
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        sanitized_line = sanitized_lines[idx]
        if in_test_item_block:
            mask[idx] = True
            test_item_depth += brace_delta(sanitized_line)
            if test_item_depth <= 0:
                in_test_item_block = False
                test_item_depth = 0
            idx += 1
            continue
        if pending_test_item:
            mask[idx] = True
            trimmed = line.strip()
            if not trimmed or trimmed.startswith("#["):
                idx += 1
                continue
            state, delta = cfg_annotated_item_state(sanitized_line)
            if state == "block":
                in_test_item_block = True
                test_item_depth = delta
                pending_test_item = False
            elif state == "complete":
                pending_test_item = False
            idx += 1
            continue
        parsed = parse_cfg_test_attribute_at(lines, idx)
        if parsed is not None:
            expr, attr_end_idx, trailing = parsed
            if has_non_negated_test_token(expr):
                attr_start_idx = attribute_stack_start(lines, idx)
                for mark_idx in range(attr_start_idx, attr_end_idx + 1):
                    mask[mark_idx] = True
                attr_line = sanitized_lines[attr_end_idx]
                delta = brace_delta(attr_line)
                if delta != 0:
                    in_test_item_block = True
                    test_item_depth = delta
                    pending_test_item = False
                else:
                    state, inner_delta = cfg_attr_state_from_trailing(trailing)
                    if state == "block":
                        in_test_item_block = True
                        test_item_depth = inner_delta
                        pending_test_item = False
                    elif state == "pending":
                        pending_test_item = True
                    else:
                        pending_test_item = False
                idx = attr_end_idx + 1
                continue
        parsed = parse_test_item_attribute_at(lines, idx)
        if parsed is not None:
            _, attr_end_idx, trailing = parsed
            attr_start_idx = attribute_stack_start(lines, idx)
            for mark_idx in range(attr_start_idx, attr_end_idx + 1):
                mask[mark_idx] = True
            state, delta = cfg_attr_state_from_trailing(trailing)
            if state == "block":
                in_test_item_block = True
                test_item_depth = delta
                pending_test_item = False
            elif state == "complete":
                pending_test_item = False
            else:
                pending_test_item = True
            idx = attr_end_idx + 1
            continue
        if is_tests_module_decl(line):
            mask[idx] = True
            delta = brace_delta(sanitized_line)
            if delta != 0:
                in_test_item_block = True
                test_item_depth = delta
        idx += 1
    return mask

for path in load_candidate_paths(candidates_file):
    if should_skip(path):
        continue
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        continue
    raw_lines = source.splitlines()
    sanitized_lines = strip_comments_and_strings(source).splitlines()
    if len(sanitized_lines) < len(raw_lines):
        sanitized_lines.extend([""] * (len(raw_lines) - len(sanitized_lines)))
    mask = compute_test_line_mask(raw_lines, sanitized_lines)
    for line_no, (raw_line, sanitized_line) in enumerate(zip(raw_lines, sanitized_lines), start=1):
        if mask[line_no - 1]:
            continue
        if EXCLUDE is not None and EXCLUDE.search(raw_line):
            continue
        if TOKEN.search(sanitized_line):
            violations.append(f"{path}:{line_no}:{raw_line}")

if violations:
    for line in violations[:5]:
        print(line)
    raise SystemExit(1)
PY
  then
    echo "$_pass_msg"
  else
    echo "$_fail_msg"
  fi
  rm -f -- "$_candidates_file"
}

parser_aware_banned_scan '\.unwrap(_err|_unchecked)?[[:space:]]*\(' '// INVARIANT:' "✓ No panic-inducing unwrap family" "ERROR: panic-inducing unwrap family found"
parser_aware_banned_scan '\.expect(_err)?[[:space:]]*\(' '// INVARIANT:' "✓ No panic-inducing expect family" "ERROR: panic-inducing expect family found"
parser_aware_banned_scan 'panic!\(' "" "✓ No panic!()" "ERROR: panic!() found"
parser_aware_banned_scan 'unimplemented!\(' "" "✓ No unimplemented!()" "ERROR: unimplemented!() found"
parser_aware_banned_scan 'unreachable!\(' '// INVARIANT:' "✓ No bare unreachable!()" "ERROR: bare unreachable!() found"
found_banned=$(find . -name 'banned_family.rs' -path '*/tests/*' -not -path '*/target/*' -print -quit)
if [ -n "$found_banned" ] \
  && grep -qF '("assert_eq", MatchKind::MacroOnly),' "$found_banned" \
  && grep -qF '("assert_ne", MatchKind::MacroOnly),' "$found_banned" \
  && grep -qF '("assert", MatchKind::MacroOnly),' "$found_banned" \
  && [ "${VERIFY_RUN_TESTS:-true}" = "true" ]; then
  echo "✓ No assert macros outside tests (delegated to banned_family.rs)"
else
  parser_aware_banned_scan '(^|[^[:alnum:]_])assert(_eq|_ne)?![[:space:]]*\(' '// INVARIANT:' "✓ No assert macros outside tests" "ERROR: assert macros outside tests found"
fi
# banned_family.rs remains the stricter parser-aware backstop so inline
# #[cfg(test)] blocks and test-annotated items in src/*.rs are masked
# correctly when the installed harness includes assert-family coverage and
# the test phase will run.
rg 'std::process::exit\(' --type rust "$@" -g '!**/src/main.rs' -g '!**/src/bin/*.rs' || echo "✓ No exit() outside entrypoints"

# Placeholders
parser_aware_banned_scan 'todo!\(' "" "✓ No todo!()" "ERROR: todo!() found"

# Non-idiomatic
rg '\.map\(\|.*\|.*\.clone\(\)\)' --type rust "$@" || echo "✓ No .map(|x| x.clone())"
rg '\.map\(\|.*\|.*\.to_owned\(\)\)' --type rust "$@" || echo "✓ No .map(|x| x.to_owned())"
rg '\.iter\(\)\.count\(\)' --type rust "$@" || echo "✓ No .iter().count()"
rg '\.iter\(\)\.next\(\)' --type rust "$@" | rg -v '// ALLOW: non-slice-next' || echo "✓ No disallowed .iter().next()"
rg 'for\s+\w+\s+in\s+0\.\.[^\n]*\.len\(\)' --type rust "$@" | rg -v '// ALLOW:' || echo "✓ No index loops"
rg '\.len\(\)\s*(==|!=)\s*0' --type rust "$@" || echo "✓ No len() == 0 / len() != 0"
rg '==\s*true|==\s*false|!=\s*true|!=\s*false' --type rust "$@" || echo "✓ No verbose bool comparisons"

# Debug artifacts
parser_aware_banned_scan 'dbg!\(' "" "✓ No dbg!()" "ERROR: dbg!() found"
rg 'println!\(' --type rust "$@" -g '!**/src/main.rs' -g '!**/src/bin/*.rs' || echo "✓ No println!() outside entrypoints"
rg 'eprintln!\(' --type rust "$@" -g '!**/src/main.rs' -g '!**/src/bin/*.rs' || echo "✓ No eprintln!() outside entrypoints"
rg 'static\s+mut(\s|$)' --type rust "$@" || echo "✓ No static mut"

# Glob imports
rg '^\s*use\s+(crate|super)::\*;' --type rust "$@" || echo "✓ No glob crate/super imports"
rg '^\s*use\s+[^;]+::\*;' --type rust "$@" | rg -v 'prelude' || echo "✓ No wildcard imports"

# Parameter anti-patterns
rg 'fn.*\(&String' --type rust "$@" || echo "✓ No &String params"
rg 'fn.*\(&Vec<' --type rust "$@" || echo "✓ No &Vec<T> params"
rg 'fn.*\(&Box<' --type rust "$@" || echo "✓ No &Box<T> params"

# Public API anti-patterns
rg 'pub\s+fn[^\n]*->\s*anyhow::Result' --type rust "$@" || echo "✓ No anyhow::Result in pub API"
rg 'pub\s+fn[^\n]*->\s*Result<[^>]*,\s*anyhow::Error\s*>' --type rust "$@" || echo "✓ No anyhow::Error in pub API"
rg 'pub\s+fn[^\n]*->\s*Result<[^>]*,\s*Box<dyn\s+std::error::Error' --type rust "$@" || echo "✓ No Box<dyn Error> in pub API"

# Shell injection
rg 'Command::new\(\s*"(sh|bash|cmd)"\s*\)\s*\.arg\(\s*"(-c|/C)"\s*\)' --type rust "$@" || echo "✓ No shell injection"

# String allocation
rg 'format![[:space:]]*\([[:space:]]*"\{\}"[[:space:]]*,[[:space:]]*' --type rust "$@" || echo "✓ No avoidable format!(\"{}\", x)"
rg 'String::from\(""\)' --type rust "$@" || echo "✓ No String::from(\"\")"
rg '"".to_string\(\)' --type rust "$@" || echo "✓ No \"\".to_string()"

# Resource safety
rg 'mem::forget\(' --type rust "$@" | rg -v '// ALLOW:' || echo "✓ No mem::forget() without justification"
rg 'Box::leak\(' --type rust "$@" | rg -v '// ALLOW:' || echo "✓ No Box::leak() without justification"

# Meta
rg 'TODO' --type rust "$@" | rg -v '#[0-9]+' | rg -v 'https?://' || echo "✓ No orphan TODOs"
# The generated installed tests/banned_family.rs harness carries a justified
# module-level allow list in its header and is excluded from this line-based
# same-line // Reason: audit.
rg '#\[allow\(' --type rust "$@" \
  | rg -v '(^|/)tests/banned_family\.rs:' \
  | rg -v '// Reason:' || echo "✓ All #[allow] justified"
```

For unsafe code, use this parser-aware scan so comments and string literals do not create false positives. Prefer `python3` plus ignore-aware file discovery (`rg --files` or `git ls-files --exclude-standard`) for full coverage:

```bash
unsafe_candidates="$(mktemp "${TMPDIR:-/tmp}/rust-verify-manual-unsafe.XXXXXX")"
if command -v rg >/dev/null 2>&1; then
  rg --files --hidden -0 -g '*.rs' >"$unsafe_candidates"
elif command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git ls-files -z --cached --others --exclude-standard -- '*.rs' ':(glob)**/*.rs' >"$unsafe_candidates"
else
  find . -name '*.rs' -not -path '*/target/*' -print0 >"$unsafe_candidates"
fi

if VERIFY_CANDIDATES_FILE="$unsafe_candidates" python3 - <<'PY'
from pathlib import Path
import os
import re
import sys

SKIP_DIRS = {"target", "test", "tests", "testdata", "bench", "benches", "example", "examples", "fixture", "fixtures"}
TOKEN = re.compile(r"(^|[^A-Za-z0-9_#])unsafe([^A-Za-z0-9_]|$)")
violations = []
candidates_file = os.environ["VERIFY_CANDIDATES_FILE"]

def should_skip(path: Path) -> bool:
    if path.name == "tests.rs" or path.name.endswith("_test.rs"):
        return True
    return any(part in SKIP_DIRS for part in path.parts)

def load_candidate_paths(filename: str):
    payload = Path(filename).read_bytes()
    seen = set()
    paths = []
    for raw_path in payload.split(b"\0"):
        if not raw_path:
            continue
        decoded = raw_path.decode("utf-8", errors="surrogateescape")
        if decoded in seen:
            continue
        seen.add(decoded)
        path = Path(decoded)
        if not path.is_file():
            continue
        paths.append(path)
    return sorted(paths)

def strip_comments_and_strings(source: str) -> str:
    out = []
    i = 0
    block_depth = 0
    in_line_comment = False
    in_string = False
    in_char = False
    raw_hashes = None

    def is_lifetime_start(idx: int) -> bool:
        if idx + 1 >= len(source):
            return False
        next_ch = source[idx + 1]
        if not (next_ch.isalpha() or next_ch == "_"):
            return False
        j = idx + 2
        while j < len(source) and (source[j].isalnum() or source[j] == "_"):
            j += 1
        return not (j < len(source) and source[j] == "'")

    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else "\0"

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if block_depth:
            if ch == "/" and nxt == "*":
                block_depth += 1
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_depth -= 1
                i += 2
                continue
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if raw_hashes is not None:
            if ch == '"':
                if raw_hashes == 0:
                    raw_hashes = None
                else:
                    matched = 0
                    j = i + 1
                    while matched < raw_hashes and j < len(source) and source[j] == "#":
                        matched += 1
                        j += 1
                    if matched == raw_hashes:
                        raw_hashes = None
                        i = j
                        continue
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if in_char:
            if ch == "\\":
                i += 2
                continue
            if ch == "\n":
                in_char = False
                out.append(ch)
                i += 1
                continue
            if ch == "'":
                in_char = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_depth = 1
            i += 2
            continue
        if ch == "r":
            j = i + 1
            while j < len(source) and source[j] == "#":
                j += 1
            if j < len(source) and source[j] == '"':
                raw_hashes = j - (i + 1)
                i = j + 1
                continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            if is_lifetime_start(i):
                out.append(ch)
                i += 1
                continue
            in_char = True
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)

for path in load_candidate_paths(candidates_file):
    if should_skip(path):
        continue
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        continue
    sanitized = strip_comments_and_strings(source)
    for line_no, (raw_line, sanitized_line) in enumerate(zip(source.splitlines(), sanitized.splitlines()), start=1):
        if TOKEN.search(sanitized_line):
            violations.append(f"{path}:{line_no}:{raw_line}")

if violations:
    print("ERROR: unsafe code found in non-test files")
    for line in violations[:5]:
        print(line)
    raise SystemExit(1)
PY
then
  echo "✓ No unsafe code in non-test files"
fi
rm -f -- "$unsafe_candidates"
```

WHEN `rg` is unavailable THEN you SHALL use these grep fallbacks.
For the inline-test-sensitive banned-family subset (`unwrap*`, `expect*`, `panic!`, `unimplemented!`, `unreachable!`, `todo!`, `assert*`, `dbg!`, and `unsafe`), you SHALL continue using the parser-aware `python3` scan above because grep-style fallbacks cannot mask inline `#[cfg(test)]` blocks or test-annotated items in `src/*.rs` correctly:

```bash
# Reuse the parser-aware python helper block above for those checks.
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '\.len\(\)[[:space:]]*(==|!=)[[:space:]]*0' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE 'format![[:space:]]*\([[:space:]]*"\{\}"[[:space:]]*,[[:space:]]*' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE 'mem::forget\(' {} + | grep -v '// ALLOW:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE 'Box::leak\(' {} + | grep -v '// ALLOW:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -exec grep -nE 'TODO' {} + | grep -vE '#[0-9]+' | grep -v http || echo "✓"
# The generated installed tests/banned_family.rs harness carries a justified
# module-level allow list in its header and is excluded from this line-based
# same-line // Reason: audit.
find . -name '*.rs' -not -path '*/target/*' -exec grep -nE '#\[allow\(' {} + \
  | grep -vE '(^|/)tests/banned_family\.rs:' \
  | grep -v '// Reason:' || echo "✓"
```

## 2. Complexity check

The generated `tests/banned_family.rs` harness is intentionally excluded from large-file warnings.

```bash
FILE_SIZE_THRESHOLD=${FILE_SIZE_THRESHOLD:-300}
find . -name '*.rs' -not -path '*/target/*' -not -path '*/tests/banned_family.rs' -exec wc -l {} \; \
  | awk -v t="$FILE_SIZE_THRESHOLD" '$1 > t {print}' \
  | tee /dev/stderr | grep -q . \
  && echo "WARN: Large files — review for splitting" \
  || echo "✓ No notably large files"

ENTRYPOINT_THRESHOLD=${ENTRYPOINT_THRESHOLD:-100}
find . \( -path '*/src/main.rs' -o -path '*/src/bin/*.rs' \) -not -path '*/target/*' -print | while IFS= read -r f; do
  lines=$(wc -l < "$f")
  if [ "$lines" -gt "$ENTRYPOINT_THRESHOLD" ]; then echo "WARN: $f has $lines lines"; fi
done
```

## 3. Build, lint, and test

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace

# Confirm no remaining placeholders
rg 'todo!\(' --type rust -g '!**/test/**' -g '!**/tests/**' -g '!**/testdata/**' -g '!**/bench/**' -g '!**/benches/**' -g '!**/example/**' -g '!**/examples/**' -g '!**/fixture/**' -g '!**/fixtures/**' -g '!**/*_test.rs' -g '!**/tests.rs' && echo "ERROR" || echo "✓ No todo!()"
rg 'unimplemented!\(' --type rust -g '!**/test/**' -g '!**/tests/**' -g '!**/testdata/**' -g '!**/bench/**' -g '!**/benches/**' -g '!**/example/**' -g '!**/examples/**' -g '!**/fixture/**' -g '!**/fixtures/**' -g '!**/*_test.rs' -g '!**/tests.rs' && echo "ERROR" || echo "✓ No unimplemented!()"
```

## 4. Dependency audit

```bash
if cargo tree --version >/dev/null 2>&1; then
  cargo tree -d
  cargo tree --depth 1 | wc -l
else
  echo "SKIP: cargo-tree not installed"
fi
```
