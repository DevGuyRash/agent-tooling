//! Integration test that enforces "banned family" API constraints for this repository.

// TEMP FILE: copy into any Rust repo as `tests/banned_family.rs` (or any crate's tests/).
//
// What it does:
// - Fails the test if *non-test* Rust code contains banned-family calls.
// - Skips test-only code: `#[cfg(test)]` blocks, `mod tests { ... }`, and `tests/` dirs.
// - Use this together with clippy lints (see TEMP_BANNED_FAMILY_CLIPPY.toml) to cover
//   broader non-idiomatic patterns.
//
// Defaults:
// - Scans `crates/` if it exists; otherwise scans the workspace root.
// - You can override scan roots via env var: BANNED_FAMILY_ROOTS="src,crates,apps"
//   (comma-separated, relative to workspace root).
//
// Usage:
// - Run: `cargo test -p <crate> --test banned_family --locked`
// - Works best when your CI runs `cargo test --workspace`.
//
// Adjustments you might want:
// - Edit BANNED_PREFIXES if you want to add/remove banned families.
// - Tweak `should_skip_dir()` if your repo uses a different layout.

use std::fs;
use std::path::{Path, PathBuf};

enum MatchKind {
    MacroOrCall,
    MacroOnly,
}

const BANNED_PREFIXES: &[(&str, MatchKind)] = &[
    ("unwrap", MatchKind::MacroOrCall),
    ("expect", MatchKind::MacroOrCall),
    ("panic", MatchKind::MacroOrCall),
    ("todo", MatchKind::MacroOrCall),
    ("unimplemented", MatchKind::MacroOrCall),
    ("unreachable", MatchKind::MacroOrCall),
    ("dbg", MatchKind::MacroOnly),
];

#[test]
fn banned_family_is_absent_in_production_code() {
    let root = workspace_root().expect("workspace root");
    let scan_roots = resolve_scan_roots(&root);
    let mut violations = Vec::new();

    for root in scan_roots {
        for path in collect_rust_files(&root) {
            let source = fs::read_to_string(&path).expect("read source");
            let sanitized = strip_comments_and_strings(&source);
            let raw_lines: Vec<&str> = source.lines().collect();
            let sanitized_lines: Vec<&str> = sanitized.lines().collect();
            let skip_lines = compute_test_line_mask(&raw_lines);

            for (line_idx, line) in sanitized_lines.iter().enumerate() {
                if skip_lines.get(line_idx).copied().unwrap_or(false) {
                    continue;
                }
                let line_no = line_idx + 1;
                for (prefix, kind) in BANNED_PREFIXES {
                    if let Some(col) = find_banned_prefix(line, prefix, kind) {
                        violations.push(format!(
                            "{}:{}:{}: banned `{}` family call",
                            path.display(),
                            line_no,
                            col + 1,
                            prefix
                        ));
                    }
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
        panic!("{message}");
    }
}

fn workspace_root() -> Option<PathBuf> {
    let mut dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    loop {
        let manifest = dir.join("Cargo.toml");
        if manifest.exists() {
            if let Ok(contents) = fs::read_to_string(&manifest) {
                if contents.contains("[workspace]") {
                    return Some(dir);
                }
            }
        }
        if !dir.pop() {
            return None;
        }
    }
}

fn resolve_scan_roots(root: &Path) -> Vec<PathBuf> {
    if let Ok(value) = std::env::var("BANNED_FAMILY_ROOTS") {
        let mut roots = Vec::new();
        for part in value.split(',') {
            let trimmed = part.trim();
            if trimmed.is_empty() {
                continue;
            }
            roots.push(root.join(trimmed));
        }
        if !roots.is_empty() {
            return roots;
        }
    }

    let crates_dir = root.join("crates");
    if crates_dir.exists() {
        vec![crates_dir]
    } else {
        vec![root.to_path_buf()]
    }
}

fn collect_rust_files(root: &Path) -> Vec<PathBuf> {
    let mut files = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let entries = match fs::read_dir(&dir) {
            Ok(value) => value,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                if should_skip_dir(&path) {
                    continue;
                }
                stack.push(path);
            } else if path.extension().and_then(|ext| ext.to_str()) == Some("rs") {
                if should_skip_file(&path) {
                    continue;
                }
                files.push(path);
            }
        }
    }
    files
}

fn should_skip_dir(path: &Path) -> bool {
    path.components().any(|component| {
        let name = component.as_os_str().to_string_lossy();
        matches!(
            name.as_ref(),
            "target"
                | ".git"
                | ".local"
                | "tests"
                | "benches"
                | "examples"
                | "fixtures"
                | "vendor"
                | "node_modules"
        )
    })
}

fn should_skip_file(path: &Path) -> bool {
    if let Some(name) = path.file_name().and_then(|name| name.to_str()) {
        if name == "tests.rs" {
            return true;
        }
    }
    false
}

fn is_cfg_test_attr(line: &str) -> bool {
    let trimmed = line.trim();
    trimmed.starts_with("#[cfg(") && trimmed.contains("test")
}

fn is_tests_module_decl(line: &str) -> bool {
    let trimmed = line.trim_start();
    trimmed.starts_with("mod tests")
        || trimmed.starts_with("pub mod tests")
        || trimmed.starts_with("pub(crate) mod tests")
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

fn compute_test_line_mask(lines: &[&str]) -> Vec<bool> {
    let mut mask = vec![false; lines.len()];
    let mut pending_cfg_test = false;
    let mut in_cfg_test_block = false;
    let mut cfg_test_depth: i32 = 0;

    for (idx, line) in lines.iter().enumerate() {
        if in_cfg_test_block {
            mask[idx] = true;
            cfg_test_depth += brace_delta(line);
            if cfg_test_depth <= 0 {
                in_cfg_test_block = false;
                cfg_test_depth = 0;
            }
            continue;
        }

        if pending_cfg_test {
            mask[idx] = true;
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with("#[") {
                continue;
            }
            let delta = brace_delta(line);
            if delta != 0 {
                in_cfg_test_block = true;
                cfg_test_depth = delta;
                pending_cfg_test = false;
                continue;
            }
            if trimmed.ends_with(';') {
                pending_cfg_test = false;
            }
            continue;
        }

        if is_cfg_test_attr(line) {
            mask[idx] = true;
            pending_cfg_test = true;
            let delta = brace_delta(line);
            if delta != 0 {
                in_cfg_test_block = true;
                cfg_test_depth = delta;
                pending_cfg_test = false;
            }
            continue;
        }

        if is_tests_module_decl(line) {
            let delta = brace_delta(line);
            if delta != 0 {
                mask[idx] = true;
                in_cfg_test_block = true;
                cfg_test_depth = delta;
            }
        }
    }

    mask
}

fn is_ident_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
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
                    let mut k = j;
                    while k < bytes.len() && bytes[k].is_ascii_whitespace() {
                        k += 1;
                    }
                    if k < bytes.len() && bytes[k] == b'!' {
                        return Some(i);
                    }
                }
                MatchKind::MacroOrCall => {
                    if j < bytes.len() && bytes[j] == b'!' {
                        return Some(i);
                    }
                    let mut k = j;
                    while k < bytes.len() && bytes[k].is_ascii_whitespace() {
                        k += 1;
                    }
                    if k < bytes.len() && bytes[k] == b'(' {
                        return Some(i);
                    }
                }
            }
        }
        i += 1;
    }
    None
}

fn strip_comments_and_strings(source: &str) -> String {
    let bytes = source.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    let mut in_line_comment = false;
    let mut in_block_comment = false;
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

        if in_block_comment {
            if b == b'*' && next == b'/' {
                push_placeholder(&mut out, b);
                push_placeholder(&mut out, next);
                in_block_comment = false;
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
            in_block_comment = true;
            i += 2;
            continue;
        }

        if b == b'\'' {
            push_placeholder(&mut out, b);
            in_char = true;
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

fn push_placeholder(out: &mut Vec<u8>, b: u8) {
    if b == b'\n' {
        out.push(b'\n');
    } else {
        out.push(b' ');
    }
}
