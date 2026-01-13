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
use anyhow::{bail, Context};

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
fn banned_family_is_absent_in_production_code() -> anyhow::Result<()> {
    let root = workspace_root().context("workspace root")?;
    let scan_roots = resolve_scan_roots(&root);
    let mut violations = Vec::new();

    for root in scan_roots {
        for path in collect_rust_files(&root) {
            let source = fs::read_to_string(&path)
                .with_context(|| format!("read source {}", path.display()))?;
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
        bail!("{message}");
    }

    Ok(())
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
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
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
    let mut mask = Vec::with_capacity(lines.len());
    let mut pending_cfg_test = false;
    let mut in_cfg_test_block = false;
    let mut cfg_test_depth: i32 = 0;

    for line in lines {
        let mut skip = false;
        if in_cfg_test_block {
            skip = true;
            cfg_test_depth += brace_delta(line);
            if cfg_test_depth <= 0 {
                in_cfg_test_block = false;
                cfg_test_depth = 0;
            }
            mask.push(skip);
            continue;
        }

        if pending_cfg_test {
            skip = true;
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with("#[") {
                mask.push(skip);
                continue;
            }
            let delta = brace_delta(line);
            if delta != 0 {
                in_cfg_test_block = true;
                cfg_test_depth = delta;
                pending_cfg_test = false;
                mask.push(skip);
                continue;
            }
            if trimmed.ends_with(';') {
                pending_cfg_test = false;
            }
            mask.push(skip);
            continue;
        }

        if is_cfg_test_attr(line) {
            skip = true;
            pending_cfg_test = true;
            let delta = brace_delta(line);
            if delta != 0 {
                in_cfg_test_block = true;
                cfg_test_depth = delta;
                pending_cfg_test = false;
            }
            mask.push(skip);
            continue;
        }

        if is_tests_module_decl(line) {
            let delta = brace_delta(line);
            if delta != 0 {
                skip = true;
                in_cfg_test_block = true;
                cfg_test_depth = delta;
            }
        }

        mask.push(skip);
    }

    mask
}

const fn is_ident_char(b: u8) -> bool {
    matches!(b, b'0'..=b'9' | b'a'..=b'z' | b'A'..=b'Z' | b'_')
}

fn find_banned_prefix(line: &str, prefix: &str, kind: &MatchKind) -> Option<usize> {
    let bytes = line.as_bytes();
    let prefix_bytes = prefix.as_bytes();
    for (i, window) in bytes.windows(prefix_bytes.len()).enumerate() {
        if window != prefix_bytes {
            continue;
        }
        if i > 0 {
            if let Some(prev) = bytes.get(i.saturating_sub(1)) {
                if is_ident_char(*prev) {
                    continue;
                }
            }
        }

        let mut j = i.saturating_add(prefix_bytes.len());
        while bytes.get(j).is_some_and(|b| is_ident_char(*b)) {
            j = j.saturating_add(1);
        }

        match kind {
            MatchKind::MacroOnly => {
                let mut k = j;
                while bytes.get(k).is_some_and(u8::is_ascii_whitespace) {
                    k = k.saturating_add(1);
                }
                if bytes.get(k) == Some(&b'!') {
                    return Some(i);
                }
            }
            MatchKind::MacroOrCall => {
                if bytes.get(j) == Some(&b'!') {
                    return Some(i);
                }
                let mut k = j;
                while bytes.get(k).is_some_and(u8::is_ascii_whitespace) {
                    k = k.saturating_add(1);
                }
                if bytes.get(k) == Some(&b'(') {
                    return Some(i);
                }
            }
        }
    }
    None
}

#[derive(Copy, Clone)]
enum StripMode {
    Normal,
    LineComment,
    BlockComment { depth: usize },
    String { escape: bool },
    Char { escape: bool },
    RawString { hashes: usize },
}

type StripIter<'a> = std::iter::Peekable<std::iter::Copied<std::slice::Iter<'a, u8>>>;

struct Stripper<'a> {
    out: Vec<u8>,
    mode: StripMode,
    it: StripIter<'a>,
}

impl<'a> Stripper<'a> {
    fn new(source: &'a str) -> Self {
        Self {
            out: Vec::with_capacity(source.len()),
            mode: StripMode::Normal,
            it: source.as_bytes().iter().copied().peekable(),
        }
    }

    fn run(mut self) -> String {
        while let Some(b) = self.it.next() {
            self.step(b);
        }
        String::from_utf8_lossy(&self.out).into_owned()
    }

    fn step(&mut self, b: u8) {
        match self.mode {
            StripMode::LineComment => self.handle_line_comment(b),
            StripMode::BlockComment { depth } => self.handle_block_comment(b, depth),
            StripMode::String { escape } => self.handle_string(b, escape),
            StripMode::Char { escape } => self.handle_char(b, escape),
            StripMode::RawString { hashes } => self.handle_raw_string(b, hashes),
            StripMode::Normal => self.handle_normal(b),
        }
    }

    fn handle_line_comment(&mut self, b: u8) {
        if b == b'\n' {
            self.out.push(b'\n');
            self.mode = StripMode::Normal;
        } else {
            push_placeholder(&mut self.out, b);
        }
    }

    fn handle_block_comment(&mut self, b: u8, depth: usize) {
        if b == b'/' && self.it.peek() == Some(&b'*') {
            push_placeholder(&mut self.out, b);
            self.it.next();
            push_placeholder(&mut self.out, b'*');
            self.mode = StripMode::BlockComment {
                depth: depth.saturating_add(1),
            };
            return;
        }

        if b == b'*' && self.it.peek() == Some(&b'/') {
            push_placeholder(&mut self.out, b);
            self.it.next();
            push_placeholder(&mut self.out, b'/');
            let depth = depth.saturating_sub(1);
            self.mode = if depth == 0 {
                StripMode::Normal
            } else {
                StripMode::BlockComment { depth }
            };
            return;
        }

        push_placeholder(&mut self.out, b);
        self.mode = StripMode::BlockComment { depth };
    }

    fn handle_string(&mut self, b: u8, escape: bool) {
        push_placeholder(&mut self.out, b);
        if escape {
            self.mode = StripMode::String { escape: false };
            return;
        }
        if b == b'\\' {
            self.mode = StripMode::String { escape: true };
            return;
        }
        if b == b'"' {
            self.mode = StripMode::Normal;
        } else {
            self.mode = StripMode::String { escape: false };
        }
    }

    fn handle_char(&mut self, b: u8, escape: bool) {
        push_placeholder(&mut self.out, b);
        if escape {
            self.mode = StripMode::Char { escape: false };
            return;
        }
        if b == b'\\' {
            self.mode = StripMode::Char { escape: true };
            return;
        }
        if b == b'\'' {
            self.mode = StripMode::Normal;
        } else {
            self.mode = StripMode::Char { escape: false };
        }
    }

    fn handle_raw_string(&mut self, b: u8, hashes: usize) {
        push_placeholder(&mut self.out, b);
        if b != b'"' {
            self.mode = StripMode::RawString { hashes };
            return;
        }
        if hashes == 0 {
            self.mode = StripMode::Normal;
            return;
        }

        let mut consumed = 0usize;
        while consumed < hashes && self.it.peek() == Some(&b'#') {
            self.it.next();
            push_placeholder(&mut self.out, b'#');
            consumed = consumed.saturating_add(1);
        }
        self.mode = if consumed == hashes {
            StripMode::Normal
        } else {
            StripMode::RawString { hashes }
        };
    }

    fn handle_normal(&mut self, b: u8) {
        if b == b'/' && self.it.peek() == Some(&b'/') {
            push_placeholder(&mut self.out, b);
            self.it.next();
            push_placeholder(&mut self.out, b'/');
            self.mode = StripMode::LineComment;
            return;
        }
        if b == b'/' && self.it.peek() == Some(&b'*') {
            push_placeholder(&mut self.out, b);
            self.it.next();
            push_placeholder(&mut self.out, b'*');
            self.mode = StripMode::BlockComment { depth: 1 };
            return;
        }
        if b == b'"' {
            push_placeholder(&mut self.out, b);
            self.mode = StripMode::String { escape: false };
            return;
        }
        if b == b'\'' {
            push_placeholder(&mut self.out, b);
            self.mode = StripMode::Char { escape: false };
            return;
        }
        if b == b'b' && self.it.peek() == Some(&b'"') {
            push_placeholder(&mut self.out, b);
            self.it.next();
            push_placeholder(&mut self.out, b'"');
            self.mode = StripMode::String { escape: false };
            return;
        }
        if b == b'b' && self.it.peek() == Some(&b'\'') {
            push_placeholder(&mut self.out, b);
            self.it.next();
            push_placeholder(&mut self.out, b'\'');
            self.mode = StripMode::Char { escape: false };
            return;
        }
        if b == b'r' || (b == b'b' && self.it.peek() == Some(&b'r')) {
            let mut buf = vec![b];
            if b == b'b' {
                self.it.next();
                buf.push(b'r');
            }

            let mut hashes = 0usize;
            while self.it.peek() == Some(&b'#') {
                self.it.next();
                buf.push(b'#');
                hashes = hashes.saturating_add(1);
            }
            if self.it.peek() == Some(&b'"') {
                self.it.next();
                buf.push(b'"');
                for byte in buf {
                    push_placeholder(&mut self.out, byte);
                }
                self.mode = StripMode::RawString { hashes };
                return;
            }
            self.out.extend(buf);
            return;
        }

        self.out.push(b);
    }
}

fn strip_comments_and_strings(source: &str) -> String {
    Stripper::new(source).run()
}

fn push_placeholder(out: &mut Vec<u8>, b: u8) {
    if b == b'\n' {
        out.push(b'\n');
    } else {
        out.push(b' ');
    }
}
