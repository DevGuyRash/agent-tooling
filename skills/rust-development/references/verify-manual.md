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

# CI workflow
git_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ -f ".github/workflows/ci.yml" ] || { [ -n "$git_root" ] && [ -f "$git_root/.github/workflows/ci.yml" ]; }; then echo "ok: CI workflow installed"; else echo "WARN: CI workflow not found (run scaffold.sh --ci)"; fi
if [ -f ".github/scripts/detect_rust_workspaces.py" ] || { [ -n "$git_root" ] && [ -f "$git_root/.github/scripts/detect_rust_workspaces.py" ]; }; then echo "ok: CI detector script installed"; else echo "WARN: CI detector script not found (run scaffold.sh --ci)"; fi

# Clippy lint config
if grep -qE '^\[workspace\.lints|^\[lints' Cargo.toml 2>/dev/null; then echo "ok: clippy lint config present"; else echo "WARN: no [workspace.lints] or [lints] in Cargo.toml (run scaffold.sh --clippy)"; fi

# [lints] workspace = true in member crates (workspace only)
if grep -qF '[workspace]' Cargo.toml 2>/dev/null; then
  missing=$(find . -name Cargo.toml -not -path '*/target/*' -not -path './Cargo.toml' -print0 2>/dev/null | while IFS= read -r -d '' m; do
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
rg 'std::process::exit\(' --type rust "$@" -g '!**/src/main.rs' -g '!**/src/bin/*.rs' || echo "✓ No exit() outside entrypoints"

# Placeholders
rg 'todo!\(' --type rust "$@" && echo "ERROR: todo!() found" || echo "✓ No todo!()"

# Non-idiomatic
rg '\.map\(\|.*\|.*\.clone\(\)\)' --type rust "$@" || echo "✓ No .map(|x| x.clone())"
rg '\.map\(\|.*\|.*\.to_owned\(\)\)' --type rust "$@" || echo "✓ No .map(|x| x.to_owned())"
rg '\.iter\(\)\.count\(\)' --type rust "$@" || echo "✓ No .iter().count()"
# NOTE: `.iter().next()` is allowed for collections without `.first()`;
# annotate intentional uses with `// ALLOW: non-slice-next`.
rg '\.iter\(\)\.next\(\)' --type rust "$@" | rg -v '// ALLOW: non-slice-next' || echo "✓ No disallowed .iter().next()"
rg 'for\s+\w+\s+in\s+0\.\.[^\n]*\.len\(\)' --type rust "$@" | rg -v '// ALLOW:' || echo "✓ No index loops"
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
rg 'unsafe\s+impl\s+(Send|Sync)' --type rust "$@" || echo "✓ No unsafe impl Send/Sync"

# Empty string allocation
rg 'String::from\(""\)' --type rust "$@" || echo "✓ No String::from(\"\")"
rg '"".to_string\(\)' --type rust "$@" || echo "✓ No \"\".to_string()"

# Orphan TODOs
rg 'TODO' --type rust "$@" | rg -v '#[0-9]+' | rg -v 'https?://' || echo "✓ No orphan TODOs"

# Unjustified allows
rg '#\[allow\(' --type rust "$@" | rg -v '// Reason:' || echo "✓ All #[allow] justified"
```

WHEN `rg` is unavailable THEN you SHALL use these grep fallbacks:

```bash
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '\.unwrap(_err|_unchecked)?[[:space:]]*\(' {} + | grep -v '// INVARIANT:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '\.expect(_err)?[[:space:]]*\(' {} + | grep -v '// INVARIANT:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nF 'panic!(' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nF 'todo!(' {} + && echo "ERROR" || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nF 'dbg!(' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -not -path '*/src/main.rs' -not -path '*/src/bin/*' -exec grep -nF 'println!(' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -not -path '*/src/main.rs' -not -path '*/src/bin/*' -exec grep -nF 'eprintln!(' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE 'static[[:space:]]+mut([[:space:]]|$)' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '^[[:space:]]*use[[:space:]]+(crate|super)::\*;' {} + || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE '^[[:space:]]*use[[:space:]]+[^;]+::\*;' {} + | grep -v prelude || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -exec grep -nE 'TODO' {} + | grep -vE '#[0-9]+' | grep -v http || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -exec grep -nE '#\[allow\(' {} + | grep -v '// Reason:' || echo "✓"
find . -name '*.rs' -not -path '*/target/*' -not -path '*/test/*' -not -path '*/tests/*' -not -path '*/testdata/*' -not -path '*/bench/*' -not -path '*/benches/*' -not -path '*/example/*' -not -path '*/examples/*' -not -path '*/fixture/*' -not -path '*/fixtures/*' -not -name '*_test.rs' -not -name 'tests.rs' -exec grep -nE 'unsafe[[:space:]]+impl[[:space:]]+(Send|Sync)' {} + || echo "✓"
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
