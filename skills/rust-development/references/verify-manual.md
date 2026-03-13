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
if [ -n "$found_banned" ]; then echo "ok: banned_family.rs installed: $found_banned"; else echo "WARN: banned_family.rs not found (run scaffold.sh --banned-test)"; fi

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
rg '\.unwrap(_err|_unchecked)?[[:space:]]*\(' --type rust "$@" | rg -v '// INVARIANT:' || echo "✓ No panic-inducing unwrap family"
rg '\.expect(_err)?[[:space:]]*\(' --type rust "$@" | rg -v '// INVARIANT:' || echo "✓ No panic-inducing expect family"
rg 'panic!\(' --type rust "$@" || echo "✓ No panic!()"
rg 'unimplemented!\(' --type rust "$@" && echo "ERROR: unimplemented!() found" || echo "✓ No unimplemented!()"
rg 'unreachable!\(' --type rust "$@" | rg -v '// INVARIANT:' || echo "✓ No bare unreachable!()"
# Assert macros outside tests are enforced by the parser-aware banned_family.rs
# harness so inline #[cfg(test)] modules in src/*.rs are masked correctly.
rg 'std::process::exit\(' --type rust "$@" -g '!**/src/main.rs' -g '!**/src/bin/*.rs' || echo "✓ No exit() outside entrypoints"

# Placeholders
rg 'todo!\(' --type rust "$@" && echo "ERROR: todo!() found" || echo "✓ No todo!()"

# Non-idiomatic
rg '\.map\(\|.*\|.*\.clone\(\)\)' --type rust "$@" || echo "✓ No .map(|x| x.clone())"
rg '\.map\(\|.*\|.*\.to_owned\(\)\)' --type rust "$@" || echo "✓ No .map(|x| x.to_owned())"
rg '\.iter\(\)\.count\(\)' --type rust "$@" || echo "✓ No .iter().count()"
rg '\.iter\(\)\.next\(\)' --type rust "$@" | rg -v '// ALLOW: non-slice-next' || echo "✓ No disallowed .iter().next()"
rg 'for\s+\w+\s+in\s+0\.\.[^\n]*\.len\(\)' --type rust "$@" | rg -v '// ALLOW:' || echo "✓ No index loops"
rg '\.len\(\)\s*(==|!=)\s*0' --type rust "$@" || echo "✓ No len() == 0 / len() != 0"
rg '==\s*true|==\s*false|!=\s*true|!=\s*false' --type rust "$@" || echo "✓ No verbose bool comparisons"

# Debug artifacts
rg 'dbg!\(' --type rust "$@" || echo "✓ No dbg!()"
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
rg '#\[allow\(' --type rust "$@" | rg -v '// Reason:' || echo "✓ All #[allow] justified"
```

For unsafe code, use this parser-aware scan so comments and string literals do not create false positives:

```bash
if python3 - <<'PY'
from pathlib import Path
import re
import sys

SKIP_DIRS = {"target", "test", "tests", "testdata", "bench", "benches", "example", "examples", "fixture", "fixtures"}
TOKEN = re.compile(r"(^|[^A-Za-z0-9_])unsafe([^A-Za-z0-9_]|$)")
violations = []

def should_skip(path: Path) -> bool:
    if path.name == "tests.rs" or path.name.endswith("_test.rs"):
        return True
    return any(part in SKIP_DIRS for part in path.parts)

def strip_comments_and_strings(source: str) -> str:
    out = []
    i = 0
    block_depth = 0
    in_line_comment = False
    in_string = False
    in_char = False
    raw_hashes = None
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
            if ch == "'":
                in_char = False
            if ch == "\n":
                out.append(ch)
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
            in_char = True
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)

for path in sorted(Path(".").rglob("*.rs")):
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
```

WHEN `rg` is unavailable THEN you SHALL use these grep fallbacks.
For `unsafe`, you SHALL continue using the parser-aware `python3` scan above because it does not depend on `rg` and avoids comment/string false positives:

```bash
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '\.unwrap(_err|_unchecked)?[[:space:]]*\(' {} + | grep -v '// INVARIANT:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '\.expect(_err)?[[:space:]]*\(' {} + | grep -v '// INVARIANT:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nF 'panic!(' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '(^|[^[:alnum:]_])assert(_eq|_ne)?![[:space:]]*\(' {} + | grep -v '// INVARIANT:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nF 'todo!(' {} + && echo "ERROR" || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '\.len\(\)[[:space:]]*(==|!=)[[:space:]]*0' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE 'format![[:space:]]*\([[:space:]]*"\{\}"[[:space:]]*,[[:space:]]*' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE 'mem::forget\(' {} + | grep -v '// ALLOW:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE 'Box::leak\(' {} + | grep -v '// ALLOW:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -exec grep -nE 'TODO' {} + | grep -vE '#[0-9]+' | grep -v http || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -exec grep -nE '#\[allow\(' {} + | grep -v '// Reason:' || echo "✓"
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
