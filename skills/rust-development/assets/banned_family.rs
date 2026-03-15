// Banned-family test harness for Rust workspaces.
// Reason: Generated test harness intentionally uses indexing, printing, and
// assertions for portability; these lints do not apply to the harness itself.
#![allow(
    clippy::collapsible_if,
    clippy::indexing_slicing,
    clippy::needless_range_loop,
    clippy::print_stderr,
    clippy::panic,
    missing_docs
)]
//
// Copy into any Rust repo as `tests/banned_family.rs` (or any crate's tests/).
//
// What it does:
// - Fails the test if *non-test* Rust code contains banned-family calls.
// - Skips test-only code: `#[cfg(test)]` blocks, test-annotated items such as
//   `#[test]` / `#[tokio::test]`, `mod tests { ... }`, and test-only
//   directories (`tests/`, `test/`, `benches/`, `examples/`, `fixtures/`).
// - Honors same-line `// INVARIANT:` escapes for `unwrap`/`expect`/`unreachable`
//   and `assert` families.
// - Treats `unsafe impl Send/Sync` as always banned in production code.
// - Use this together with clippy lints (see clippy-lints.toml) to cover
//   broader non-idiomatic patterns.
//
// Defaults:
// - Always scans the workspace root; also scans `crates/` if it exists.
// - You can override scan roots via env var: BANNED_FAMILY_ROOTS="src,crates,apps"
//   (comma-separated, relative to workspace root).
// - When `git` is available inside a repository, file discovery honors
//   `.gitignore`/exclude rules via `git ls-files --exclude-standard`.
//
// Usage:
// - Run: `cargo test -p <crate> --test banned_family --locked`
// - Works best when your CI runs `cargo test --workspace`.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

enum MatchKind {
    MacroOrCall,
    MacroOnly,
}

const BANNED_PREFIXES: &[(&str, MatchKind)] = &[
    ("unwrap", MatchKind::MacroOrCall),
    ("unwrap_err", MatchKind::MacroOrCall),
    ("unwrap_unchecked", MatchKind::MacroOrCall),
    ("expect", MatchKind::MacroOrCall),
    ("expect_err", MatchKind::MacroOrCall),
    ("panic", MatchKind::MacroOrCall),
    ("todo", MatchKind::MacroOrCall),
    ("unimplemented", MatchKind::MacroOrCall),
    ("unreachable", MatchKind::MacroOrCall),
    ("assert_eq", MatchKind::MacroOnly),
    ("assert_ne", MatchKind::MacroOnly),
    ("assert", MatchKind::MacroOnly),
    ("dbg", MatchKind::MacroOnly),
];

#[test]
fn banned_family_is_absent_in_production_code() {
    let root = workspace_root().expect("workspace root");
    let scan_roots = resolve_scan_roots(&root);
    let mut violations = Vec::new();
    let mut seen_files = HashSet::new();

    for root in scan_roots {
        for path in collect_rust_files(&root) {
            let canonical_path = match fs::canonicalize(&path) {
                Ok(canonical) => canonical,
                Err(err) => {
                    eprintln!("warn: canonicalize failed for {}: {err}", path.display());
                    path.clone()
                }
            };
            if !seen_files.insert(canonical_path) {
                continue;
            }
            let source = fs::read_to_string(&path).expect("read source");
            let sanitized = strip_comments_and_strings(&source);
            let raw_lines: Vec<&str> = source.lines().collect();
            let sanitized_lines: Vec<&str> = sanitized.lines().collect();
            let skip_lines = compute_test_line_mask(&raw_lines, &sanitized_lines);

            let mut unsafe_impl_state = UnsafeImplState::searching();
            for (line_idx, line) in sanitized_lines.iter().enumerate() {
                if skip_lines.get(line_idx).copied().unwrap_or(false) {
                    continue;
                }
                let raw_line = raw_lines.get(line_idx).copied().unwrap_or("");
                let has_invariant = raw_line.contains("// INVARIANT:");
                let line_no = line_idx + 1;
                for (prefix, kind) in BANNED_PREFIXES {
                    if let Some(col) = find_banned_prefix(line, prefix, kind) {
                        if has_invariant && is_invariant_escapable_prefix(prefix) {
                            continue;
                        }
                        violations.push(format!(
                            "{}:{}:{}: banned `{}` family call",
                            path.display(),
                            line_no,
                            col + 1,
                            prefix
                        ));
                    }
                }
                if is_unsafe_impl_send_or_sync_violation(line, &mut unsafe_impl_state) {
                    violations.push(format!(
                        "{}:{}:1: banned `unsafe impl Send/Sync`",
                        path.display(),
                        line_no,
                    ));
                }
            }
        }
    }

    if !violations.is_empty() {
        let mut message = String::from("banned-family usage found:\n");
        for violation in violations {
            message.push_str("  ");
            message.push_str(&violation);
            message.push('\n');
        }
        panic!("{}", message);
    }
}

fn workspace_root() -> Option<PathBuf> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    // clone: dir is mutated by pop(); manifest_dir remains as fallback.
    let mut dir = manifest_dir.clone();
    loop {
        let manifest = dir.join("Cargo.toml");
        let has_workspace_manifest = manifest.exists()
            && fs::read_to_string(&manifest)
                .map(|contents| contents.contains("[workspace]"))
                .unwrap_or(false);
        if has_workspace_manifest {
            return Some(dir);
        }
        if !dir.pop() {
            break;
        }
    }
    // Fall back to the crate's own manifest directory. This also covers runs
    // from workspace members where no ancestor Cargo.toml declares [workspace].
    Some(manifest_dir)
}

fn resolve_scan_roots(root: &Path) -> Vec<PathBuf> {
    let canonical_root = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    if let Ok(value) = std::env::var("BANNED_FAMILY_ROOTS") {
        let mut roots = Vec::new();
        for part in value.split(',') {
            let trimmed = part.trim();
            if trimmed.is_empty() {
                continue;
            }
            let requested = Path::new(trimmed);
            if requested.is_absolute() {
                continue;
            }
            let candidate = root.join(requested);
            let canonical_candidate = match fs::canonicalize(&candidate) {
                Ok(path) => path,
                Err(_) => continue,
            };
            if !canonical_candidate.starts_with(&canonical_root) {
                continue;
            }
            if canonical_candidate.is_dir() {
                roots.push(canonical_candidate);
            }
        }
        if !roots.is_empty() {
            return roots;
        }
    }

    let mut roots = vec![root.to_path_buf()];
    let crates_dir = root.join("crates");
    if crates_dir.is_dir() {
        roots.push(crates_dir);
    }
    roots
}

fn collect_rust_files(root: &Path) -> Vec<PathBuf> {
    if let Some(files) = collect_git_rust_files(root) {
        return files;
    }

    let mut files = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    let mut visited_dirs = HashSet::new();
    while let Some(dir) = stack.pop() {
        let canonical_dir = match fs::canonicalize(&dir) {
            Ok(path) => path,
            Err(_) => continue,
        };
        if !visited_dirs.insert(canonical_dir) {
            continue;
        }
        let entries = match fs::read_dir(&dir) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let mut sorted_entries = Vec::new();
        for entry in entries {
            match entry {
                Ok(value) => sorted_entries.push(value),
                Err(err) => {
                    eprintln!(
                        "warning: failed to read an entry under {}: {err}",
                        dir.display()
                    );
                }
            }
        }
        sorted_entries.sort_by_key(|entry| entry.path());
        for entry in sorted_entries {
            let path = entry.path();
            let file_type = match entry.file_type() {
                Ok(value) => value,
                Err(_) => continue,
            };
            if file_type.is_symlink() {
                continue;
            }
            if file_type.is_dir() {
                if should_skip_dir(&path) {
                    continue;
                }
                stack.push(path);
            } else if file_type.is_file()
                && path.extension().and_then(|ext| ext.to_str()) == Some("rs")
            {
                if should_skip_file(&path) {
                    continue;
                }
                files.push(path);
            }
        }
    }
    files.sort_unstable();
    files
}

fn collect_git_rust_files(root: &Path) -> Option<Vec<PathBuf>> {
    let output = Command::new("git")
        .arg("ls-files")
        .arg("-z")
        .arg("--cached")
        .arg("--others")
        .arg("--exclude-standard")
        .arg("--")
        .arg("*.rs")
        .arg(":(glob)**/*.rs")
        .current_dir(root)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }

    let mut files = Vec::new();
    let mut seen = HashSet::new();
    for raw_path in output.stdout.split(|byte| *byte == 0) {
        if raw_path.is_empty() {
            continue;
        }
        let relative = PathBuf::from(String::from_utf8_lossy(raw_path).into_owned());
        let path = root.join(relative);
        if !path.is_file() {
            continue;
        }
        if should_skip_dir(&path) || should_skip_file(&path) {
            continue;
        }
        let canonical = fs::canonicalize(&path).unwrap_or_else(|_| path.clone());
        if seen.insert(canonical) {
            files.push(path);
        }
    }
    files.sort_unstable();
    Some(files)
}

fn should_skip_dir(path: &Path) -> bool {
    path.components().any(|component| {
        let name = component.as_os_str().to_string_lossy();
        matches!(
            name.as_ref(),
            "target" | ".git" | ".local" | "vendor" | "node_modules"
        ) || is_test_only_component(name.as_ref())
    })
}

fn should_skip_file(path: &Path) -> bool {
    if path
        .parent()
        .map(|parent| {
            parent.components().any(|component| {
                let segment = component.as_os_str().to_string_lossy();
                is_test_only_component(segment.as_ref())
            })
        })
        .unwrap_or(false)
    {
        return true;
    }

    let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
        return false;
    };
    name == "tests.rs" || name.ends_with("_test.rs")
}

fn is_test_only_component(name: &str) -> bool {
    matches!(
        name,
        "test"
            | "tests"
            | "testdata"
            | "bench"
            | "benches"
            | "example"
            | "examples"
            | "fixture"
            | "fixtures"
    )
}

#[derive(Default)]
struct AttrScanState {
    paren_depth: usize,
    bracket_depth: usize,
    brace_depth: usize,
    in_string: bool,
    in_char: bool,
    escaped: bool,
    raw_hashes: Option<usize>,
}

fn raw_string_start(segment: &str) -> Option<(usize, usize)> {
    let bytes = segment.as_bytes();
    let mut idx = match bytes.first().copied()? {
        b'r' => 1,
        b'b' if bytes.get(1).copied() == Some(b'r') => 2,
        _ => return None,
    };

    let mut hash_count = 0usize;
    while bytes.get(idx).copied() == Some(b'#') {
        hash_count += 1;
        idx += 1;
    }

    if bytes.get(idx).copied() != Some(b'"') {
        return None;
    }

    Some((idx + 1, hash_count))
}

fn raw_string_end_len(segment: &str, hash_count: usize) -> Option<usize> {
    let bytes = segment.as_bytes();
    if bytes.first().copied() != Some(b'"') {
        return None;
    }

    for offset in 0..hash_count {
        if bytes.get(offset + 1).copied() != Some(b'#') {
            return None;
        }
    }

    Some(hash_count + 1)
}

fn find_top_level_attr_closing_bracket(segment: &str, state: &mut AttrScanState) -> Option<usize> {
    let mut iter = segment.char_indices().peekable();
    while let Some((idx, ch)) = iter.next() {
        if let Some(hash_count) = state.raw_hashes {
            if let Some(end_len) = raw_string_end_len(&segment[idx..], hash_count) {
                state.raw_hashes = None;
                for _ in 1..end_len {
                    iter.next();
                }
            }
            continue;
        }

        if state.in_string {
            if state.escaped {
                state.escaped = false;
                continue;
            }
            match ch {
                '\\' => state.escaped = true,
                '"' => state.in_string = false,
                _ => {}
            }
            continue;
        }

        if state.in_char {
            if state.escaped {
                state.escaped = false;
                continue;
            }
            match ch {
                '\\' => state.escaped = true,
                '\'' => state.in_char = false,
                _ => {}
            }
            continue;
        }

        match ch {
            'r' | 'b' => {
                if let Some((start_len, hash_count)) = raw_string_start(&segment[idx..]) {
                    state.raw_hashes = Some(hash_count);
                    for _ in 1..start_len {
                        iter.next();
                    }
                }
            }
            '"' => state.in_string = true,
            '\'' => state.in_char = true,
            '(' => state.paren_depth += 1,
            ')' => {
                if state.paren_depth > 0 {
                    state.paren_depth -= 1;
                }
            }
            '[' => state.bracket_depth += 1,
            ']' => {
                if state.paren_depth == 0 && state.brace_depth == 0 && state.bracket_depth == 0 {
                    return Some(idx);
                }
                if state.bracket_depth > 0 {
                    state.bracket_depth -= 1;
                }
            }
            '{' => state.brace_depth += 1,
            '}' => {
                if state.brace_depth > 0 {
                    state.brace_depth -= 1;
                }
            }
            _ => {}
        }
    }
    None
}

fn parse_outer_attribute_at(
    lines: &[&str],
    start_idx: usize,
    initial_remainder: &str,
) -> Option<(String, usize, String)> {
    let mut remainder = initial_remainder.strip_prefix("#[")?;
    let mut attr = String::new();
    let mut idx = start_idx;
    let mut scan_state = AttrScanState::default();

    loop {
        if let Some(end_idx) = find_top_level_attr_closing_bracket(remainder, &mut scan_state) {
            let before_end = remainder[..end_idx].trim();
            if !before_end.is_empty() {
                if !attr.is_empty() {
                    attr.push(' ');
                }
                attr.push_str(before_end);
            }
            let trailing = remainder[end_idx + 1..].trim_start().to_string();
            return Some((attr, idx, trailing));
        }

        let chunk = remainder.trim();
        if !chunk.is_empty() {
            if !attr.is_empty() {
                attr.push(' ');
            }
            attr.push_str(chunk);
        }

        idx += 1;
        if idx >= lines.len() {
            return None;
        }
        remainder = lines[idx].trim();
    }
}

fn parse_cfg_test_attribute_at(
    lines: &[&str],
    start_idx: usize,
) -> Option<(String, usize, String)> {
    let mut idx = start_idx;
    let mut remainder = lines[start_idx].trim().to_string();

    loop {
        let (attr, attr_end_idx, trailing) =
            parse_outer_attribute_at(lines, idx, remainder.as_str())?;
        let attr_name = attr
            .split_once('(')
            .map(|(name, _)| name)
            .unwrap_or(attr.as_str());
        if attr_name.trim() == "cfg" {
            if let Some((_, expr)) = attr.split_once('(') {
                let cfg_expr = expr.trim_end().trim_end_matches(')').trim().to_string();
                return Some((cfg_expr, attr_end_idx, trailing));
            }
            return None;
        }
        remainder = trailing.trim_start().to_string();
        if !remainder.starts_with("#[") {
            return None;
        }
        idx = attr_end_idx;
    }
}

fn parse_test_item_attribute_at(
    lines: &[&str],
    start_idx: usize,
) -> Option<(String, usize, String)> {
    let mut idx = start_idx;
    let mut remainder = lines[start_idx].trim().to_string();

    loop {
        let (attr, attr_end_idx, trailing) =
            parse_outer_attribute_at(lines, idx, remainder.as_str())?;
        if attr.is_empty() {
            return None;
        }
        let attr_name = attr
            .split_once('(')
            .map(|(name, _)| name)
            .unwrap_or(attr.as_str());
        let is_test_attr = attr_name
            .trim()
            .rsplit("::")
            .next()
            .map(|terminal| terminal == "test")
            .unwrap_or(false);
        if is_test_attr {
            return Some((attr, attr_end_idx, trailing));
        }
        remainder = trailing.trim_start().to_string();
        if !remainder.starts_with("#[") {
            return None;
        }
        idx = attr_end_idx;
    }
}

fn has_non_negated_test_token(expr: &str) -> bool {
    let compact: String = expr
        .chars()
        .filter(|ch| !ch.is_ascii_whitespace())
        .collect();
    let bytes = compact.as_bytes();
    let mut idx = 0usize;
    let mut in_string = false;
    let mut stack: Vec<(bool, bool)> = Vec::new();

    while idx < bytes.len() {
        let b = bytes[idx];
        if in_string {
            if b == b'\\' && idx + 1 < bytes.len() {
                idx += 2;
                continue;
            }
            if b == b'"' {
                in_string = false;
            }
            idx += 1;
            continue;
        }

        if b == b'"' {
            in_string = true;
            idx += 1;
            continue;
        }

        if is_ident_char(b) {
            let start = idx;
            idx += 1;
            while idx < bytes.len() && is_ident_char(bytes[idx]) {
                idx += 1;
            }
            let ident = &compact[start..idx];
            if idx < bytes.len() && bytes[idx] == b'(' {
                let is_not = ident == "not";
                let is_any = ident == "any";
                stack.push((is_not, is_any));
                idx += 1;
                continue;
            }
            if ident == "test" {
                let negated = stack.iter().any(|(is_not, _)| *is_not);
                let inside_any = stack.iter().any(|(_, is_any)| *is_any);
                if !negated && !inside_any {
                    return true;
                }
            }
            continue;
        }

        if b == b'(' {
            stack.push((false, false));
        } else if b == b')' {
            stack.pop();
        }
        idx += 1;
    }

    false
}

fn is_cfg_test_attr(line: &str) -> bool {
    let single = [line];
    parse_cfg_test_attribute_at(&single, 0)
        .map(|(expr, _, _)| has_non_negated_test_token(&expr))
        .unwrap_or(false)
}

fn is_test_item_attr(line: &str) -> bool {
    let single = [line];
    parse_test_item_attribute_at(&single, 0).is_some()
}

fn is_tests_module_decl(line: &str) -> bool {
    let trimmed = line.trim_start();
    const TEST_MODULE_PREFIXES: &[&str] = &["mod tests", "pub mod tests", "pub(crate) mod tests"];
    TEST_MODULE_PREFIXES.iter().any(|prefix| {
        if !trimmed.starts_with(prefix) {
            return false;
        }
        let remainder = &trimmed[prefix.len()..];
        match remainder.chars().next() {
            None => true,
            Some('{') | Some(';') => true,
            Some(ch) if ch.is_whitespace() => true,
            Some(_) => false,
        }
    })
}

fn brace_delta(line: &str) -> i32 {
    let mut delta = 0;
    for ch in line.chars() {
        match ch {
            '{' => delta += 1,
            '}' => delta -= 1,
            _ => {}
        }
    }
    delta
}

enum CfgAnnotatedItemState {
    Pending,
    Complete,
    Block(i32),
}

fn cfg_annotated_item_state(line: &str) -> CfgAnnotatedItemState {
    if line.contains('{') {
        let delta = brace_delta(line);
        if delta > 0 {
            return CfgAnnotatedItemState::Block(delta);
        }
        return CfgAnnotatedItemState::Complete;
    }
    if line.contains(';') {
        return CfgAnnotatedItemState::Complete;
    }
    CfgAnnotatedItemState::Pending
}

fn cfg_attr_state_from_trailing(trailing: &str) -> CfgAnnotatedItemState {
    let trimmed = trailing.trim();
    if trimmed.is_empty() {
        CfgAnnotatedItemState::Pending
    } else {
        cfg_annotated_item_state(trimmed)
    }
}

fn attribute_stack_start(lines: &[&str], idx: usize) -> usize {
    let mut start = idx;
    while start > 0 {
        let prev = lines[start - 1].trim();
        if !prev.starts_with("#[") {
            break;
        }
        start -= 1;
    }
    start
}

fn compute_test_line_mask(lines: &[&str], sanitized_lines: &[&str]) -> Vec<bool> {
    let mut mask = vec![false; lines.len()];
    let mut pending_test_item = false;
    let mut in_test_item_block = false;
    let mut test_item_depth: i32 = 0;

    let mut idx = 0usize;
    while idx < lines.len() {
        let line = lines[idx];
        if in_test_item_block {
            mask[idx] = true;
            test_item_depth += brace_delta(sanitized_lines[idx]);
            if test_item_depth <= 0 {
                in_test_item_block = false;
                test_item_depth = 0;
            }
            idx += 1;
            continue;
        }

        if pending_test_item {
            mask[idx] = true;
            let trimmed = line.trim();
            // Keep pending state across blank lines and stacked attributes until
            // the test-only item (module/use/type/function/etc.) is observed.
            if trimmed.is_empty() || trimmed.starts_with("#[") {
                idx += 1;
                continue;
            }
            match cfg_annotated_item_state(sanitized_lines[idx]) {
                CfgAnnotatedItemState::Block(delta) => {
                    in_test_item_block = true;
                    test_item_depth = delta;
                    pending_test_item = false;
                }
                CfgAnnotatedItemState::Complete => {
                    pending_test_item = false;
                }
                CfgAnnotatedItemState::Pending => {
                    pending_test_item = true;
                }
            }
            idx += 1;
            continue;
        }

        if let Some((expr, attr_end_idx, trailing)) = parse_cfg_test_attribute_at(lines, idx) {
            if has_non_negated_test_token(&expr) {
                let attr_start_idx = attribute_stack_start(lines, idx);
                for item in mask.iter_mut().take(attr_end_idx + 1).skip(attr_start_idx) {
                    *item = true;
                }
                let delta = brace_delta(sanitized_lines[attr_end_idx]);
                if delta != 0 {
                    in_test_item_block = true;
                    test_item_depth = delta;
                    pending_test_item = false;
                } else {
                    match cfg_attr_state_from_trailing(&trailing) {
                        CfgAnnotatedItemState::Block(inner_delta) => {
                            in_test_item_block = true;
                            test_item_depth = inner_delta;
                            pending_test_item = false;
                        }
                        CfgAnnotatedItemState::Complete => {
                            pending_test_item = false;
                        }
                        CfgAnnotatedItemState::Pending => {
                            pending_test_item = true;
                        }
                    }
                }
                idx = attr_end_idx + 1;
                continue;
            }
        }

        if let Some((_, attr_end_idx, trailing)) = parse_test_item_attribute_at(lines, idx) {
            let attr_start_idx = attribute_stack_start(lines, idx);
            for item in mask.iter_mut().take(attr_end_idx + 1).skip(attr_start_idx) {
                *item = true;
            }
            match cfg_attr_state_from_trailing(&trailing) {
                CfgAnnotatedItemState::Block(delta) => {
                    in_test_item_block = true;
                    test_item_depth = delta;
                    pending_test_item = false;
                }
                CfgAnnotatedItemState::Complete => {
                    pending_test_item = false;
                }
                CfgAnnotatedItemState::Pending => {
                    pending_test_item = true;
                }
            }
            idx = attr_end_idx + 1;
            continue;
        }

        if is_tests_module_decl(line) {
            mask[idx] = true;
            let delta = brace_delta(sanitized_lines[idx]);
            if delta != 0 {
                in_test_item_block = true;
                test_item_depth = delta;
            }
        }
        idx += 1;
    }

    mask
}

fn is_ident_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

fn is_invariant_escapable_prefix(prefix: &str) -> bool {
    matches!(
        prefix,
        "unwrap"
            | "unwrap_err"
            | "unwrap_unchecked"
            | "expect"
            | "expect_err"
            | "unreachable"
            | "assert"
            | "assert_eq"
            | "assert_ne"
    )
}

fn find_banned_prefix(line: &str, prefix: &str, kind: &MatchKind) -> Option<usize> {
    let bytes = line.as_bytes();
    let prefix_bytes = prefix.as_bytes();
    let mut i = 0;
    while i + prefix_bytes.len() <= bytes.len() {
        if &bytes[i..i + prefix_bytes.len()] == prefix_bytes {
            if i > 0 && is_ident_char(bytes[i - 1]) {
                i += 1;
                continue;
            }
            let mut j = i + prefix_bytes.len();
            while j < bytes.len() && is_ident_char(bytes[j]) {
                j += 1;
            }
            match kind {
                MatchKind::MacroOnly => {
                    if j != i + prefix_bytes.len() {
                        i += 1;
                        continue;
                    }
                    let mut k = j;
                    while k < bytes.len() && bytes[k].is_ascii_whitespace() {
                        k += 1;
                    }
                    if k < bytes.len() && bytes[k] == b'!' {
                        return Some(i);
                    }
                }
                MatchKind::MacroOrCall => {
                    let mut k = j;
                    while k < bytes.len() && bytes[k].is_ascii_whitespace() {
                        k += 1;
                    }
                    if k < bytes.len() && bytes[k] == b'!' {
                        return Some(i);
                    }
                    if j == i + prefix_bytes.len() {
                        let mut call_idx = j;
                        while call_idx < bytes.len() && bytes[call_idx].is_ascii_whitespace() {
                            call_idx += 1;
                        }
                        if call_idx < bytes.len() && bytes[call_idx] == b'(' {
                            return Some(i);
                        }
                    }
                }
            }
        }
        i += 1;
    }
    None
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum UnsafeImplPhase {
    Searching,
    SawUnsafe,
    SawUnsafeImpl,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct UnsafeImplState {
    phase: UnsafeImplPhase,
    // Only meaningful when `phase == SawUnsafeImpl`.
    impl_generic_depth: usize,
}

impl UnsafeImplState {
    fn searching() -> Self {
        Self {
            phase: UnsafeImplPhase::Searching,
            impl_generic_depth: 0,
        }
    }

    fn set_phase(&mut self, phase: UnsafeImplPhase) {
        self.phase = phase;
        if phase != UnsafeImplPhase::SawUnsafeImpl {
            self.impl_generic_depth = 0;
        }
    }
}

fn contains_unsafe_impl_send_or_sync(line: &str, state: &mut UnsafeImplState) -> bool {
    let mut i = 0;
    let bytes = line.as_bytes();
    while i < bytes.len() {
        let b = bytes[i];
        if b.is_ascii_alphabetic() || b == b'_' {
            let start = i;
            i += 1;
            while i < bytes.len() && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_') {
                i += 1;
            }
            let token = &line[start..i];
            let next_phase = match (state.phase, token) {
                (_, "unsafe") => UnsafeImplPhase::SawUnsafe,
                (UnsafeImplPhase::SawUnsafe, "impl") => UnsafeImplPhase::SawUnsafeImpl,
                (UnsafeImplPhase::SawUnsafeImpl, "for") => UnsafeImplPhase::Searching,
                (UnsafeImplPhase::SawUnsafeImpl, "where") => UnsafeImplPhase::Searching,
                (UnsafeImplPhase::SawUnsafeImpl, "Send" | "Sync")
                    if state.impl_generic_depth == 0 =>
                {
                    return true;
                }
                (UnsafeImplPhase::SawUnsafe, _) => UnsafeImplPhase::Searching,
                _ => state.phase,
            };
            state.set_phase(next_phase);
            continue;
        }
        if state.phase == UnsafeImplPhase::SawUnsafeImpl {
            if b == b'<' {
                state.impl_generic_depth += 1;
                i += 1;
                continue;
            }
            if b == b'>' && state.impl_generic_depth > 0 {
                state.impl_generic_depth -= 1;
                i += 1;
                continue;
            }
        }
        if matches!(b, b';' | b'{' | b'}') {
            state.set_phase(UnsafeImplPhase::Searching);
        }
        i += 1;
    }
    false
}

fn is_unsafe_impl_send_or_sync_violation(
    sanitized_line: &str,
    state: &mut UnsafeImplState,
) -> bool {
    if !contains_unsafe_impl_send_or_sync(sanitized_line, state) {
        return false;
    }
    state.set_phase(UnsafeImplPhase::Searching);
    true
}

fn strip_comments_and_strings(source: &str) -> String {
    let bytes = source.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    let mut in_line_comment = false;
    let mut block_comment_depth = 0usize;
    let mut in_string = false;
    let mut in_char = false;
    let mut raw_hashes: Option<usize> = None;

    while i < bytes.len() {
        let b = bytes[i];
        let next = bytes.get(i + 1).copied().unwrap_or(b'\0');

        if in_line_comment {
            if b == b'\n' {
                in_line_comment = false;
                out.push(b);
            } else {
                push_placeholder(&mut out, b);
            }
            i += 1;
            continue;
        }

        if block_comment_depth > 0 {
            if b == b'/' && next == b'*' {
                push_placeholder(&mut out, b);
                push_placeholder(&mut out, next);
                block_comment_depth += 1;
                i += 2;
            } else if b == b'*' && next == b'/' {
                push_placeholder(&mut out, b);
                push_placeholder(&mut out, next);
                block_comment_depth -= 1;
                i += 2;
            } else {
                push_placeholder(&mut out, b);
                i += 1;
            }
            continue;
        }

        if let Some(hashes) = raw_hashes {
            if b == b'"' {
                if hashes == 0 {
                    push_placeholder(&mut out, b);
                    raw_hashes = None;
                    i += 1;
                    continue;
                }
                let mut matches = 0;
                let mut j = i + 1;
                while matches < hashes && j < bytes.len() && bytes[j] == b'#' {
                    matches += 1;
                    j += 1;
                }
                if matches == hashes {
                    push_placeholder(&mut out, b);
                    for _ in 0..hashes {
                        push_placeholder(&mut out, b'#');
                    }
                    raw_hashes = None;
                    i = j;
                    continue;
                }
            }
            push_placeholder(&mut out, b);
            i += 1;
            continue;
        }

        if in_string {
            if b == b'\\' {
                push_placeholder(&mut out, b);
                if i + 1 < bytes.len() {
                    push_placeholder(&mut out, bytes[i + 1]);
                    i += 2;
                } else {
                    i += 1;
                }
                continue;
            }
            push_placeholder(&mut out, b);
            if b == b'"' {
                in_string = false;
            }
            i += 1;
            continue;
        }

        if in_char {
            if b == b'\\' {
                push_placeholder(&mut out, b);
                if i + 1 < bytes.len() {
                    push_placeholder(&mut out, bytes[i + 1]);
                    i += 2;
                } else {
                    i += 1;
                }
                continue;
            }
            push_placeholder(&mut out, b);
            if b == b'\n' {
                in_char = false;
            }
            if b == b'\'' {
                in_char = false;
            }
            i += 1;
            continue;
        }

        if b == b'/' && next == b'/' {
            push_placeholder(&mut out, b);
            push_placeholder(&mut out, next);
            in_line_comment = true;
            i += 2;
            continue;
        }
        if b == b'/' && next == b'*' {
            push_placeholder(&mut out, b);
            push_placeholder(&mut out, next);
            block_comment_depth = 1;
            i += 2;
            continue;
        }

        if b == b'\'' {
            if is_lifetime_start(bytes, i) {
                out.push(b);
            } else {
                push_placeholder(&mut out, b);
                in_char = true;
            }
            i += 1;
            continue;
        }

        if b == b'"' {
            push_placeholder(&mut out, b);
            in_string = true;
            i += 1;
            continue;
        }

        if b == b'r' || (b == b'b' && next == b'r') {
            let mut j = i + 1;
            if b == b'b' {
                j += 1;
            }
            let mut hashes = 0usize;
            while j < bytes.len() && bytes[j] == b'#' {
                hashes += 1;
                j += 1;
            }
            if j < bytes.len() && bytes[j] == b'"' {
                push_placeholder(&mut out, b);
                if b == b'b' {
                    push_placeholder(&mut out, next);
                }
                for _ in 0..hashes {
                    push_placeholder(&mut out, b'#');
                }
                push_placeholder(&mut out, b'"');
                raw_hashes = Some(hashes);
                i = j + 1;
                continue;
            }
        }

        out.push(b);
        i += 1;
    }

    String::from_utf8_lossy(&out).to_string()
}

fn is_lifetime_start(bytes: &[u8], quote_idx: usize) -> bool {
    if quote_idx + 1 >= bytes.len() {
        return false;
    }
    let next = bytes[quote_idx + 1];
    if !(next.is_ascii_alphabetic() || next == b'_') {
        return false;
    }
    let mut idx = quote_idx + 2;
    while idx < bytes.len() && is_ident_char(bytes[idx]) {
        idx += 1;
    }
    bytes.get(idx).copied() != Some(b'\'')
}

fn push_placeholder(out: &mut Vec<u8>, b: u8) {
    if b == b'\n' {
        out.push(b'\n');
    } else {
        out.push(b' ');
    }
}

#[cfg(test)]
mod tests {
    use super::{
        collect_rust_files, compute_test_line_mask, contains_unsafe_impl_send_or_sync,
        find_banned_prefix, is_cfg_test_attr, is_test_item_attr, parse_cfg_test_attribute_at,
        parse_test_item_attribute_at, resolve_scan_roots, should_skip_file,
        strip_comments_and_strings, MatchKind,
    };
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_temp_dir(label: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or(0);
        std::env::temp_dir().join(format!(
            "banned-family-{label}-{}-{}",
            std::process::id(),
            nanos
        ))
    }

    #[test]
    fn cfg_test_single_line_item_does_not_mask_following_production_code() {
        let lines = vec![
            "#[cfg(test)]",
            "fn test_setup() {}",
            "",
            "fn prod() { panic!(\"bug\"); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, false, false]);
    }

    #[test]
    fn cfg_not_test_attr_is_not_treated_as_test_only() {
        assert!(!is_cfg_test_attr("#[cfg(not(test))]"));
    }

    #[test]
    fn cfg_any_test_with_non_test_branch_is_not_treated_as_test_only() {
        assert!(!is_cfg_test_attr("#[cfg(any(test, feature = \"bench\"))]"));
    }

    #[test]
    fn cfg_not_any_test_attr_is_not_treated_as_test_only() {
        assert!(!is_cfg_test_attr(
            "#[cfg(not(any(test, feature = \"bench\")))]"
        ));
    }

    #[test]
    fn cfg_feature_string_named_test_is_not_treated_as_cfg_test() {
        assert!(!is_cfg_test_attr("#[cfg(feature = \"test\")]"));
    }

    #[test]
    fn bare_test_attribute_masks_only_annotated_item() {
        let lines = vec![
            "#[test]",
            "fn helper() {",
            "    assert_eq!(2 + 2, 4);",
            "    unsafe { touch(); }",
            "}",
            "fn prod() { panic!(\"should be scanned\"); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, true, false]);
    }

    #[test]
    fn stacked_attributes_above_test_item_are_masked() {
        let lines = vec![
            "#[allow(dead_code)]",
            "#[test]",
            "fn helper()",
            "{",
            "    assert_eq!(left, right);",
            "}",
            "fn prod() { assert_eq!(left, right); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, true, true, false]);
    }

    #[test]
    fn same_line_stacked_test_attribute_is_masked() {
        let lines = vec![
            "#[allow(dead_code)] #[test] fn helper() {",
            "    panic!(\"only in tests\");",
            "}",
            "fn prod() { panic!(\"should be scanned\"); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, false]);
    }

    #[test]
    fn multiline_non_test_attribute_with_trailing_test_attribute_is_detected() {
        let lines = vec!["#[doc = concat(", "    \"helper\"", ")] #[test]"];
        assert_eq!(
            parse_test_item_attribute_at(&lines, 0),
            Some((
                "test".to_string(),
                2,
                String::new(),
            ))
        );
    }

    #[test]
    fn multiline_non_test_attribute_with_trailing_test_attribute_is_masked() {
        let lines = vec![
            "#[doc = concat(",
            "    \"helper\"",
            ")] #[test]",
            "fn helper() {",
            "    panic!(\"only in tests\");",
            "}",
            "fn prod() { panic!(\"should be scanned\"); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, true, true, false]);
    }

    #[test]
    fn path_qualified_test_attribute_masks_only_annotated_item() {
        let lines = vec![
            "#[tokio::test(flavor = \"current_thread\")]",
            "async fn helper() {",
            "    dbg ! (42);",
            "}",
            "fn prod() { dbg ! (42); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, false]);
    }

    #[test]
    fn bare_and_path_qualified_test_attributes_are_detected() {
        assert!(is_test_item_attr("#[test]"));
        assert!(is_test_item_attr("#[tokio::test]"));
        assert!(is_test_item_attr(
            "#[tokio::test(flavor = \"current_thread\")]"
        ));
        assert!(!is_test_item_attr("#[cfg(test)]"));
        assert!(!is_test_item_attr("#[test_case]"));
    }

    #[test]
    fn multiline_path_qualified_test_attribute_is_detected() {
        let lines = vec!["#[tokio::test(", "    flavor = \"current_thread\"", ")]"];
        assert_eq!(
            parse_test_item_attribute_at(&lines, 0),
            Some((
                "tokio::test( flavor = \"current_thread\" )".to_string(),
                2,
                String::new(),
            ))
        );
    }

    #[test]
    fn multiline_path_qualified_test_attribute_masks_only_annotated_item() {
        let lines = vec![
            "#[tokio::test(",
            "    flavor = \"current_thread\"",
            ")]",
            "async fn helper() {",
            "    dbg ! (42);",
            "    unsafe { touch(); }",
            "}",
            "fn prod() { dbg ! (42); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, true, true, true, false]);
    }

    #[test]
    fn test_attribute_with_inner_array_masks_only_annotated_item() {
        let lines = vec![
            "#[cases::test(cases = [1, 2])]",
            "fn helper() {",
            "    assert_eq!(left, right);",
            "}",
            "fn prod() { assert_eq!(left, right); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, false]);
    }

    #[test]
    fn test_attribute_with_raw_string_masks_only_annotated_item() {
        let lines = vec![
            "#[tokio::test(name = r#\"case ] one\"#)]",
            "async fn helper() {",
            "    dbg ! (42);",
            "}",
            "fn prod() { dbg ! (42); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, false]);
    }

    #[test]
    fn multiline_cfg_test_attribute_masks_only_test_item() {
        let lines = vec![
            "#[cfg(",
            "    test,",
            ")]",
            "fn helper() { panic!(\"only in tests\"); }",
            "fn prod() { panic!(\"should be scanned\"); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, false]);
    }

    #[test]
    fn multiline_cfg_test_with_trailing_comment_masks_following_item() {
        let raw = [
            "#[cfg(",
            "    test",
            ")] // keep",
            "fn helper() { panic!(\"only in tests\"); }",
            "fn prod() { panic!(\"should be scanned\"); }",
        ];
        let source = raw.join("\n");
        let sanitized_source = strip_comments_and_strings(&source);
        let raw_lines: Vec<&str> = source.lines().collect();
        let sanitized_lines: Vec<&str> = sanitized_source.lines().collect();
        let mask = compute_test_line_mask(&raw_lines, &sanitized_lines);
        assert_eq!(mask, vec![true, true, true, true, false]);
    }

    #[test]
    fn cfg_test_brace_on_next_line_masks_entire_item() {
        let lines = vec![
            "#[cfg(test)]",
            "fn helper()",
            "{",
            "    panic!(\"only in tests\");",
            "}",
            "fn prod() { panic!(\"should be scanned\"); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, true, false]);
    }

    #[test]
    fn same_line_stacked_cfg_test_attribute_is_masked() {
        let lines = vec![
            "#[allow(dead_code)] #[cfg(test)] fn helper() {",
            "    panic!(\"only in tests\");",
            "}",
            "fn prod() { panic!(\"should be scanned\"); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, false]);
    }

    #[test]
    fn same_line_stacked_cfg_test_attr_is_detected() {
        assert!(is_cfg_test_attr(
            "#[allow(dead_code)] #[cfg(test)] fn helper() {}"
        ));
    }

    #[test]
    fn multiline_non_test_attribute_with_trailing_cfg_test_attribute_is_detected() {
        let lines = vec!["#[doc = concat(", "    \"helper\"", ")] #[cfg(test)]"];
        assert_eq!(
            parse_cfg_test_attribute_at(&lines, 0),
            Some((
                "test".to_string(),
                2,
                String::new(),
            ))
        );
    }

    #[test]
    fn multiline_non_test_attribute_with_trailing_cfg_test_attribute_is_masked() {
        let lines = vec![
            "#[doc = concat(",
            "    \"helper\"",
            ")] #[cfg(test)]",
            "fn helper() {",
            "    panic!(\"only in tests\");",
            "}",
            "fn prod() { panic!(\"should be scanned\"); }",
        ];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, true, true, true, true, true, false]);
    }

    #[test]
    fn lifetime_annotations_do_not_mask_following_code() {
        let source = "fn conn() -> &'static str { value.unwrap() }";
        let sanitized = strip_comments_and_strings(source);
        assert!(sanitized.contains("value.unwrap()"));
    }

    #[test]
    fn multiline_lifetime_bounds_do_not_mask_following_code() {
        let source = "fn borrow<'a, 'b>()\nwhere\n    'a: 'b,\n{\n    value.unwrap();\n}";
        let sanitized = strip_comments_and_strings(source);
        assert!(sanitized.contains("value.unwrap();"));
    }

    #[test]
    fn unterminated_char_literal_does_not_mask_following_lines() {
        let source = "let broken = 'x;\nunsafe { touch(); }\n";
        let sanitized = strip_comments_and_strings(source);
        assert!(sanitized.contains("unsafe { touch(); }"));
    }

    #[test]
    fn find_banned_prefix_detects_unwrap_expect_err_variants() {
        assert_eq!(
            find_banned_prefix("value.unwrap_err()", "unwrap_err", &MatchKind::MacroOrCall),
            Some(6)
        );
        assert_eq!(
            find_banned_prefix(
                "unsafe { value.unwrap_unchecked() }",
                "unwrap_unchecked",
                &MatchKind::MacroOrCall
            ),
            Some(15)
        );
        assert_eq!(
            find_banned_prefix(
                "result.expect_err(\"boom\")",
                "expect_err",
                &MatchKind::MacroOrCall
            ),
            Some(7)
        );
    }

    #[test]
    fn find_banned_prefix_detects_assert_macro_variants() {
        assert_eq!(
            find_banned_prefix("assert!(ready);", "assert", &MatchKind::MacroOnly),
            Some(0)
        );
        assert_eq!(
            find_banned_prefix(
                "assert_eq!(left, right);",
                "assert_eq",
                &MatchKind::MacroOnly
            ),
            Some(0)
        );
        assert_eq!(
            find_banned_prefix(
                "assert_ne!(left, right);",
                "assert_ne",
                &MatchKind::MacroOnly
            ),
            Some(0)
        );
        assert_eq!(
            find_banned_prefix("assert_eq!(left, right);", "assert", &MatchKind::MacroOnly),
            None
        );
        assert_eq!(
            find_banned_prefix(
                "assert_eq ! (left, right);",
                "assert_eq",
                &MatchKind::MacroOnly
            ),
            Some(0)
        );
        assert_eq!(
            find_banned_prefix("dbg ! (value);", "dbg", &MatchKind::MacroOnly),
            Some(0)
        );
    }

    #[test]
    fn find_banned_prefix_does_not_match_similar_non_banned_names() {
        assert_eq!(
            find_banned_prefix(
                "value.unwrap_or_default()",
                "unwrap",
                &MatchKind::MacroOrCall
            ),
            None
        );
        assert_eq!(
            find_banned_prefix("ctx.expectation()", "expect", &MatchKind::MacroOrCall),
            None
        );
        assert_eq!(
            find_banned_prefix("debug_assert!(ready);", "assert", &MatchKind::MacroOnly),
            None
        );
        assert_eq!(
            find_banned_prefix(
                "assert_matches!(value, Some(_));",
                "assert",
                &MatchKind::MacroOnly
            ),
            None
        );
    }

    #[test]
    fn should_skip_file_for_test_helpers_in_tests_dir() {
        assert!(should_skip_file(Path::new("src/tests/helpers.rs")));
        assert!(should_skip_file(Path::new("crates/api/fixtures/setup.rs")));
        assert!(!should_skip_file(Path::new("src/testing.rs")));
    }

    #[test]
    fn collect_rust_files_respects_gitignored_generated_dirs() {
        if Command::new("git").arg("--version").output().is_err() {
            return;
        }

        let root = unique_temp_dir("gitignore-scan");
        fs::create_dir_all(root.join("src")).expect("create src dir");
        fs::create_dir_all(root.join(".generated")).expect("create ignored dir");
        fs::write(root.join("src/lib.rs"), "pub fn live() {}").expect("write src file");
        fs::write(
            root.join(".generated/ghost.rs"),
            "pub fn ghost() { todo!(); }",
        )
        .expect("write ignored file");
        fs::write(root.join(".gitignore"), ".generated/\n").expect("write gitignore");

        let init_status = Command::new("git")
            .arg("init")
            .arg("-q")
            .current_dir(&root)
            .status()
            .expect("run git init");
        assert!(init_status.success(), "git init should succeed");

        let files = collect_rust_files(&root);
        assert_eq!(files, vec![root.join("src/lib.rs")]);

        fs::remove_dir_all(&root).expect("cleanup temp workspace");
    }

    #[test]
    fn collect_rust_files_skips_deleted_tracked_git_paths() {
        if Command::new("git").arg("--version").output().is_err() {
            return;
        }

        let root = unique_temp_dir("git-deleted-scan");
        fs::create_dir_all(root.join("src")).expect("create src dir");
        fs::write(root.join("src/live.rs"), "pub fn live() {}").expect("write live file");
        fs::write(root.join("src/deleted.rs"), "pub fn deleted() {}").expect("write deleted file");

        let init_status = Command::new("git")
            .arg("init")
            .arg("-q")
            .current_dir(&root)
            .status()
            .expect("run git init");
        assert!(init_status.success(), "git init should succeed");

        let add_status = Command::new("git")
            .arg("add")
            .arg("src/deleted.rs")
            .current_dir(&root)
            .status()
            .expect("track deleted candidate");
        assert!(add_status.success(), "git add should succeed");

        fs::remove_file(root.join("src/deleted.rs")).expect("delete tracked file");

        let files = collect_rust_files(&root);
        assert_eq!(files, vec![root.join("src/live.rs")]);

        fs::remove_dir_all(&root).expect("cleanup temp workspace");
    }

    #[test]
    fn tests_module_declaration_line_is_masked() {
        let lines = vec!["mod tests;", "fn prod() { panic!(\"bug\"); }"];
        let mask = compute_test_line_mask(&lines, &lines);
        assert_eq!(mask, vec![true, false]);
    }

    #[test]
    fn resolve_scan_roots_includes_root_and_crates_for_mixed_layout() {
        let root = unique_temp_dir("roots");
        let src_dir = root.join("src");
        let crates_dir = root.join("crates");
        fs::create_dir_all(&src_dir).expect("create root src");
        fs::create_dir_all(&crates_dir).expect("create crates dir");
        fs::write(src_dir.join("lib.rs"), "pub fn root_pkg() {}").expect("write root src");

        let roots = resolve_scan_roots(&root);
        assert_eq!(roots.len(), 2);
        assert_eq!(roots[0], root);
        assert_eq!(roots[1], crates_dir);

        fs::remove_dir_all(&root).expect("cleanup temp workspace");
    }

    #[test]
    fn unsafe_impl_send_sync_detection_is_token_aware() {
        let mut state = super::UnsafeImplState::searching();
        assert!(contains_unsafe_impl_send_or_sync(
            "unsafe impl Send for Worker {}",
            &mut state
        ));
        state = super::UnsafeImplState::searching();
        assert!(contains_unsafe_impl_send_or_sync(
            "unsafe impl<T> Sync for Cache<T> {}",
            &mut state
        ));
        let sanitized = strip_comments_and_strings("let msg = \"unsafe impl Send\";");
        state = super::UnsafeImplState::searching();
        assert!(!contains_unsafe_impl_send_or_sync(&sanitized, &mut state));
        state = super::UnsafeImplState::searching();
        assert!(!contains_unsafe_impl_send_or_sync(
            "impl Send for Worker {}",
            &mut state
        ));
    }

    #[test]
    fn unsafe_impl_send_sync_detection_spans_multiple_lines() {
        let mut state = super::UnsafeImplState::searching();
        assert!(!super::is_unsafe_impl_send_or_sync_violation(
            "unsafe impl<T>",
            &mut state
        ));
        assert!(super::is_unsafe_impl_send_or_sync_violation(
            "Send for Worker<T> {}",
            &mut state
        ));
        assert!(!super::is_unsafe_impl_send_or_sync_violation(
            "let keep_scanning = Send;",
            &mut state
        ));
    }

    #[test]
    fn unsafe_impl_send_sync_detection_ignores_generic_bounds() {
        let mut state = super::UnsafeImplState::searching();
        assert!(!contains_unsafe_impl_send_or_sync(
            "unsafe impl<T: Send + Sync> Service for Worker<T> {}",
            &mut state
        ));
        state = super::UnsafeImplState::searching();
        assert!(!contains_unsafe_impl_send_or_sync(
            "unsafe impl<T>",
            &mut state
        ));
        assert!(!contains_unsafe_impl_send_or_sync(
            "Service for Worker<T>",
            &mut state
        ));
        assert!(!contains_unsafe_impl_send_or_sync(
            "where T: Send + Sync {}",
            &mut state
        ));
    }

    #[test]
    fn unsafe_impl_comments_do_not_create_exceptions() {
        let raw = "unsafe impl Send for Worker {} // SAFETY: still forbidden";
        let sanitized = strip_comments_and_strings(raw);
        let mut state = super::UnsafeImplState::searching();
        assert!(super::is_unsafe_impl_send_or_sync_violation(
            &sanitized, &mut state
        ));
    }

    #[test]
    fn unsafe_impl_comment_markers_in_strings_still_fail() {
        let raw = "static DOCS: &str = \"// SAFETY: fake\"; unsafe impl Send for Worker {}";
        let sanitized = strip_comments_and_strings(raw);
        let mut state = super::UnsafeImplState::searching();
        assert!(super::is_unsafe_impl_send_or_sync_violation(
            &sanitized, &mut state
        ));
    }

    #[test]
    fn unsafe_impl_comment_markers_in_block_comments_still_fail() {
        let raw = "/* // SAFETY: fake */ unsafe impl Send for Worker {}";
        let sanitized = strip_comments_and_strings(raw);
        let mut state = super::UnsafeImplState::searching();
        assert!(super::is_unsafe_impl_send_or_sync_violation(
            &sanitized, &mut state
        ));
    }

    #[test]
    fn unsafe_impl_multiline_sequences_remain_violations_even_with_comments() {
        let mut state = super::UnsafeImplState::searching();
        let raw_impl_line = "unsafe impl<T> // SAFETY: still forbidden";
        let impl_line = strip_comments_and_strings(raw_impl_line);
        assert!(!super::is_unsafe_impl_send_or_sync_violation(
            &impl_line, &mut state
        ));
        assert_eq!(state.phase, super::UnsafeImplPhase::SawUnsafeImpl);
        let raw_send_line = "Send for Worker<T> {}";
        assert!(super::is_unsafe_impl_send_or_sync_violation(
            raw_send_line,
            &mut state
        ));
    }

    #[test]
    fn nested_block_comments_remain_sanitized() {
        let source = "/* outer /* nested unsafe impl Send */ still comment */\nfn ok() {}";
        let sanitized = strip_comments_and_strings(source);
        assert!(!sanitized.contains("unsafe impl Send"));
    }
}
