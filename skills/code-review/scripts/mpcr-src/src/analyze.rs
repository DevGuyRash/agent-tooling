//! Language-agnostic static analysis for code review workers.
//!
//! All checks are purely text-based (no AST parsing, no external deps).
//! Workers run these on their assigned files to surface mechanical findings
//! before theorem generation, improving signal quality.

use serde::Serialize;
use std::collections::HashMap;

// ── Output types ─────────────────────────────────────────────────────────────

/// A single static analysis finding.
#[derive(Debug, Serialize)]
pub struct AnalysisFinding {
    /// Name of the check that produced this finding.
    pub check: String,
    /// File path where the finding was detected.
    pub file: String,
    /// Line number (1-based) of the finding.
    pub line: usize,
    /// Truncated line excerpt for context.
    pub excerpt: String,
    /// Human-readable explanation of the finding.
    pub detail: String,
}

/// Summary of all analysis checks on a file set.
#[derive(Debug, Serialize)]
pub struct AnalysisReport {
    /// Number of files analyzed.
    pub files_scanned: usize,
    /// Total lines across all files.
    pub total_lines: usize,
    /// All individual findings from line-level checks.
    pub findings: Vec<AnalysisFinding>,
    /// Duplicate text blocks found across files.
    pub duplicate_blocks: Vec<DuplicateBlock>,
    /// Functions with high nesting or branching.
    pub complexity_hotspots: Vec<ComplexityHotspot>,
    /// Subset of findings matching dead-code or unreachable patterns.
    pub dead_markers: Vec<AnalysisFinding>,
}

/// A block of text duplicated across locations.
#[derive(Debug, Serialize)]
pub struct DuplicateBlock {
    /// Hash fingerprint of the duplicated text.
    pub fingerprint: String,
    /// All locations where this block appears.
    pub locations: Vec<DuplicateLocation>,
    /// Number of consecutive lines in the block.
    pub line_count: usize,
}

/// A specific location of a duplicated block.
#[derive(Debug, Serialize)]
pub struct DuplicateLocation {
    /// File path containing the duplicate.
    pub file: String,
    /// Starting line number (1-based).
    pub start_line: usize,
}

/// A function/block with high nesting or branching complexity.
#[derive(Debug, Serialize)]
pub struct ComplexityHotspot {
    /// File path containing the hotspot.
    pub file: String,
    /// Starting line number (1-based).
    pub start_line: usize,
    /// Best-effort extracted function/method name.
    pub name_hint: String,
    /// Maximum brace-nesting depth within the function.
    pub max_nesting: usize,
    /// Count of branch keywords (if/else/match/case).
    pub branch_count: usize,
}

// ── Analysis engine ──────────────────────────────────────────────────────────

/// Run all static checks on the given file contents.
///
/// `files` maps relative path → file content.
///
/// # Errors
/// Returns an error only if the analysis itself fails (not for findings).
pub fn run_all(files: &HashMap<String, String>) -> anyhow::Result<AnalysisReport> {
    let mut findings = Vec::new();
    let mut total_lines = 0usize;

    for (path, content) in files {
        let lines: Vec<&str> = content.lines().collect();
        total_lines += lines.len();
        check_dead_code_markers(&lines, path, &mut findings);
        check_todo_fixme(&lines, path, &mut findings);
        check_long_functions(&lines, path, &mut findings);
        check_long_lines(&lines, path, &mut findings);
        check_unreachable_markers(&lines, path, &mut findings);
    }

    let duplicate_blocks = find_duplicate_blocks(files);
    let complexity_hotspots = find_complexity_hotspots(files);
    let dead_markers: Vec<AnalysisFinding> = findings
        .iter()
        .filter(|f| f.check == "dead-code-marker" || f.check == "unreachable-marker")
        .map(|f| AnalysisFinding {
            check: f.check.clone(),
            file: f.file.clone(),
            line: f.line,
            excerpt: f.excerpt.clone(),
            detail: f.detail.clone(),
        })
        .collect();

    Ok(AnalysisReport {
        files_scanned: files.len(),
        total_lines,
        findings,
        duplicate_blocks,
        complexity_hotspots,
        dead_markers,
    })
}

/// Run a single named check. Returns only findings from that check.
pub fn run_check(
    files: &HashMap<String, String>,
    check_name: &str,
) -> anyhow::Result<Vec<AnalysisFinding>> {
    let mut findings = Vec::new();
    for (path, content) in files {
        let lines: Vec<&str> = content.lines().collect();
        match check_name {
            "dead-code" => check_dead_code_markers(&lines, path, &mut findings),
            "todos" => check_todo_fixme(&lines, path, &mut findings),
            "long-functions" => check_long_functions(&lines, path, &mut findings),
            "long-lines" => check_long_lines(&lines, path, &mut findings),
            "unreachable" => check_unreachable_markers(&lines, path, &mut findings),
            _ => return Err(anyhow::anyhow!("unknown check: {check_name}")),
        }
    }
    Ok(findings)
}

/// List available check names.
pub fn available_checks() -> Vec<(&'static str, &'static str)> {
    vec![
        (
            "dead-code",
            "Detect dead code markers (#[dead_code], #if 0, if False, etc.)",
        ),
        ("todos", "Surface TODO/FIXME/HACK/XXX/SAFETY annotations"),
        (
            "long-functions",
            "Flag functions/methods exceeding 60 lines",
        ),
        ("long-lines", "Flag lines exceeding 120 characters"),
        (
            "unreachable",
            "Detect unreachable code markers (unreachable!, panic!, todo!)",
        ),
        (
            "duplicates",
            "Find duplicate text blocks (≥4 lines) across files",
        ),
        (
            "complexity",
            "Identify high-nesting/high-branching hotspots",
        ),
    ]
}

// ── Individual checks ────────────────────────────────────────────────────────

/// Detect language-agnostic dead code markers.
fn check_dead_code_markers(lines: &[&str], path: &str, out: &mut Vec<AnalysisFinding>) {
    let markers = [
        "#[allow(dead_code)]",
        "#[cfg(never)]",
        "// DEAD CODE",
        "/* DEAD CODE",
        "#if 0",
        "if False:",
        "if (false)",
        "if false {",
        "// unused",
        "# unused",
        "// deprecated",
        "// @deprecated",
        "/* @deprecated",
        "/// @deprecated",
    ];
    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim().to_ascii_lowercase();
        if is_probable_string_literal_line(line) {
            continue;
        }
        let lower_line = line.to_ascii_lowercase();
        for marker in &markers {
            let marker_lower = marker.to_ascii_lowercase();
            if trimmed.contains(&marker_lower) {
                if is_marker_inside_double_quotes(&lower_line, &marker_lower) {
                    continue;
                }
                out.push(AnalysisFinding {
                    check: "dead-code-marker".to_string(),
                    file: path.to_string(),
                    line: idx + 1,
                    excerpt: truncate_line(line, 100),
                    detail: format!("Matched dead-code pattern: {marker}"),
                });
                break;
            }
        }
    }
}

/// Surface TODO/FIXME/HACK/XXX/SAFETY comments.
fn check_todo_fixme(lines: &[&str], path: &str, out: &mut Vec<AnalysisFinding>) {
    let tags = ["TODO", "FIXME", "HACK", "XXX", "SAFETY"];
    for (idx, line) in lines.iter().enumerate() {
        let upper = line.to_ascii_uppercase();
        for tag in &tags {
            if upper.contains(tag) {
                let is_comment = line.trim().starts_with("//")
                    || line.trim().starts_with('#')
                    || line.trim().starts_with("/*")
                    || line.trim().starts_with('*')
                    || line.trim().starts_with("<!--");
                if is_comment {
                    out.push(AnalysisFinding {
                        check: "todo-fixme".to_string(),
                        file: path.to_string(),
                        line: idx + 1,
                        excerpt: truncate_line(line, 100),
                        detail: format!("{tag} annotation found"),
                    });
                    break;
                }
            }
        }
    }
}

/// Flag functions/methods/blocks exceeding 60 lines.
fn check_long_functions(lines: &[&str], path: &str, out: &mut Vec<AnalysisFinding>) {
    let threshold = 60;
    let fn_patterns = [
        "fn ",
        "def ",
        "func ",
        "function ",
        "sub ",
        "method ",
        "public ",
        "private ",
        "protected ",
        "static ",
    ];
    let mut func_start: Option<(usize, String)> = None;
    let mut brace_depth: i32 = 0;
    let mut indent_start: Option<usize> = None;
    let mut saw_open_brace = false;

    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with("//") || trimmed.starts_with('#') {
            continue;
        }

        let is_fn_start = fn_patterns.iter().any(|p| trimmed.starts_with(p))
            || (trimmed.contains("fn ") && (trimmed.contains('(') || trimmed.contains('{')));

        if is_fn_start && func_start.is_none() {
            let name = extract_name_hint(trimmed);
            func_start = Some((idx + 1, name));
            brace_depth = 0;
            indent_start = Some(line.len() - line.trim_start().len());
            saw_open_brace = false;
        }

        let open_braces = trimmed.chars().filter(|&c| c == '{').count() as i32;
        let close_braces = trimmed.chars().filter(|&c| c == '}').count() as i32;
        if open_braces > 0 {
            saw_open_brace = true;
        }
        brace_depth += open_braces;
        brace_depth -= close_braces;

        if let Some((start, ref name)) = func_start {
            let func_len = idx + 1 - start;
            let at_brace_end = saw_open_brace && brace_depth <= 0 && func_len > 1;
            let at_dedent = !saw_open_brace
                && indent_start.is_some_and(|is| {
                    let current_indent = line.len() - line.trim_start().len();
                    current_indent <= is && func_len > 1 && !trimmed.is_empty()
                });

            if at_brace_end || at_dedent {
                if func_len > threshold {
                    out.push(AnalysisFinding {
                        check: "long-function".to_string(),
                        file: path.to_string(),
                        line: start,
                        excerpt: format!("{name} ({func_len} lines)"),
                        detail: format!(
                            "Function exceeds {threshold}-line threshold ({func_len} lines)"
                        ),
                    });
                }
                func_start = None;
                indent_start = None;
                saw_open_brace = false;
            }
        }
    }

    if let Some((start, ref name)) = func_start {
        let func_len = lines.len() + 1 - start;
        if func_len > threshold {
            out.push(AnalysisFinding {
                check: "long-function".to_string(),
                file: path.to_string(),
                line: start,
                excerpt: format!("{name} ({func_len} lines)"),
                detail: format!("Function exceeds {threshold}-line threshold ({func_len} lines)"),
            });
        }
    }
}

/// Flag lines exceeding 120 characters.
fn check_long_lines(lines: &[&str], path: &str, out: &mut Vec<AnalysisFinding>) {
    let threshold = 120;
    let mut count = 0u32;
    for (idx, line) in lines.iter().enumerate() {
        if line.len() > threshold {
            count += 1;
            if count <= 5 {
                out.push(AnalysisFinding {
                    check: "long-line".to_string(),
                    file: path.to_string(),
                    line: idx + 1,
                    excerpt: truncate_line(line, 80),
                    detail: format!("Line is {} chars (threshold: {threshold})", line.len()),
                });
            }
        }
    }
    if count > 5 {
        out.push(AnalysisFinding {
            check: "long-line".to_string(),
            file: path.to_string(),
            line: 0,
            excerpt: String::new(),
            detail: format!("{count} lines exceed {threshold} chars (showing first 5)"),
        });
    }
}

/// Detect unreachable/panic/todo! markers in code.
fn check_unreachable_markers(lines: &[&str], path: &str, out: &mut Vec<AnalysisFinding>) {
    let markers = [
        "unreachable!(",
        "unreachable!()",
        "todo!(",
        "todo!()",
        "unimplemented!(",
        "unimplemented!()",
        "panic!(",
        "raise NotImplementedError",
        "throw new Error(\"not implemented",
        "throw new Error(\"unreachable",
    ];
    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if is_probable_string_literal_line(line) {
            continue;
        }
        if trimmed.starts_with("//") || trimmed.starts_with('#') || trimmed.starts_with("/*") {
            continue;
        }
        let lower_line = line.to_ascii_lowercase();
        for marker in &markers {
            if trimmed.contains(marker) {
                if is_marker_inside_double_quotes(&lower_line, &marker.to_ascii_lowercase()) {
                    continue;
                }
                out.push(AnalysisFinding {
                    check: "unreachable-marker".to_string(),
                    file: path.to_string(),
                    line: idx + 1,
                    excerpt: truncate_line(line, 100),
                    detail: format!("Matched unreachable pattern: {marker}"),
                });
                break;
            }
        }
    }
}

// ── Cross-file checks ────────────────────────────────────────────────────────

/// Find duplicate text blocks (≥4 consecutive non-blank lines) across files.
pub fn find_duplicate_blocks(files: &HashMap<String, String>) -> Vec<DuplicateBlock> {
    let min_block = 4;
    let mut fingerprints: HashMap<u64, Vec<DuplicateLocation>> = HashMap::new();

    for (path, content) in files {
        let lines: Vec<&str> = content.lines().collect();
        if lines.len() < min_block {
            continue;
        }
        for start in 0..=lines.len().saturating_sub(min_block) {
            let block: Vec<&str> = lines[start..start + min_block]
                .iter()
                .map(|l| l.trim())
                .collect();
            if block.iter().all(|l| l.is_empty()) {
                continue;
            }
            if block.iter().any(|l| l.is_empty()) {
                continue;
            }
            let hash = simple_hash(&block.join("\n"));
            fingerprints
                .entry(hash)
                .or_default()
                .push(DuplicateLocation {
                    file: path.clone(),
                    start_line: start + 1,
                });
        }
    }

    let mut duplicates = Vec::new();
    for (hash, locations) in &fingerprints {
        if locations.len() < 2 {
            continue;
        }
        let mut deduped: Vec<&DuplicateLocation> = Vec::new();
        for loc in locations {
            let dominated = deduped.iter().any(|existing| {
                existing.file == loc.file
                    && loc.start_line > existing.start_line
                    && loc.start_line < existing.start_line + min_block
            });
            if !dominated {
                deduped.push(loc);
            }
        }
        if deduped.len() >= 2 {
            duplicates.push(DuplicateBlock {
                fingerprint: format!("{hash:016x}"),
                locations: deduped
                    .iter()
                    .map(|l| DuplicateLocation {
                        file: l.file.clone(),
                        start_line: l.start_line,
                    })
                    .collect(),
                line_count: min_block,
            });
        }
    }
    duplicates.sort_by(|a, b| b.locations.len().cmp(&a.locations.len()));
    duplicates.truncate(20);
    duplicates
}

/// Identify functions/blocks with high nesting depth or high branch count.
pub fn find_complexity_hotspots(files: &HashMap<String, String>) -> Vec<ComplexityHotspot> {
    let mut hotspots = Vec::new();

    for (path, content) in files {
        let lines: Vec<&str> = content.lines().collect();
        let fn_patterns = ["fn ", "def ", "func ", "function "];
        let branch_patterns = [
            "if ", "else ", "elif ", "else if", "match ", "case ", "switch ",
        ];

        let mut func_start: Option<(usize, String)> = None;
        let mut max_nesting: usize = 0;
        let mut branch_count: usize = 0;
        let mut base_depth: i32 = 0;
        let mut depth: i32 = 0;

        for (idx, line) in lines.iter().enumerate() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with("//") {
                continue;
            }

            let is_fn = fn_patterns.iter().any(|p| trimmed.starts_with(p));

            if is_fn {
                if let Some((start, ref name)) = func_start {
                    if max_nesting > 4 || branch_count > 10 {
                        hotspots.push(ComplexityHotspot {
                            file: path.clone(),
                            start_line: start,
                            name_hint: name.clone(),
                            max_nesting,
                            branch_count,
                        });
                    }
                }
                func_start = Some((idx + 1, extract_name_hint(trimmed)));
                base_depth = depth;
                max_nesting = 0;
                branch_count = 0;
            }

            depth += trimmed.chars().filter(|&c| c == '{').count() as i32;
            depth -= trimmed.chars().filter(|&c| c == '}').count() as i32;

            if func_start.is_some() {
                let relative = (depth - base_depth).max(0) as usize;
                if relative > max_nesting {
                    max_nesting = relative;
                }
                if branch_patterns
                    .iter()
                    .any(|p| trimmed.starts_with(p) || trimmed.contains(p))
                {
                    branch_count += 1;
                }
            }
        }
        if let Some((start, ref name)) = func_start {
            if max_nesting > 4 || branch_count > 10 {
                hotspots.push(ComplexityHotspot {
                    file: path.clone(),
                    start_line: start,
                    name_hint: name.clone(),
                    max_nesting,
                    branch_count,
                });
            }
        }
    }

    hotspots.sort_by(|a, b| {
        b.max_nesting
            .cmp(&a.max_nesting)
            .then(b.branch_count.cmp(&a.branch_count))
    });
    hotspots.truncate(10);
    hotspots
}

// ── Helpers ──────────────────────────────────────────────────────────────────

fn truncate_line(line: &str, max: usize) -> String {
    let trimmed = line.trim();
    if trimmed.len() <= max {
        return trimmed.to_string();
    }
    let boundary = max.saturating_sub(3);
    let safe_end = trimmed
        .char_indices()
        .take_while(|(i, _)| *i <= boundary)
        .last()
        .map_or(0, |(i, _)| i);
    format!("{}...", &trimmed[..safe_end])
}

fn extract_name_hint(line: &str) -> String {
    let cleaned = line
        .replace("pub ", "")
        .replace("async ", "")
        .replace("pub(crate) ", "");
    let parts: Vec<&str> = cleaned.split('(').collect();
    let before_paren = parts[0].trim();
    let tokens: Vec<&str> = before_paren.split_whitespace().collect();
    match tokens.last() {
        Some(name) => name.to_string(),
        None => before_paren.to_string(),
    }
}

fn simple_hash(text: &str) -> u64 {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for byte in text.bytes() {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x0100_0000_01b3);
    }
    hash
}

fn is_probable_string_literal_line(line: &str) -> bool {
    let trimmed = line.trim_start();
    trimmed.starts_with('"')
        || trimmed.starts_with("r\"")
        || trimmed.starts_with("r#\"")
        || trimmed.starts_with("b\"")
}

fn is_marker_inside_double_quotes(line: &str, marker: &str) -> bool {
    let Some(marker_idx) = line.find(marker) else {
        return false;
    };
    let before = &line[..marker_idx];
    let after = &line[marker_idx + marker.len()..];
    let quote_before = before.rfind('"');
    let quote_after = after.find('"');
    match (quote_before, quote_after) {
        (Some(_), Some(_)) => {
            // Marker is wrapped by a quote before and after, e.g. `let x = "#if 0";`.
            true
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dead_code_marker_detection() {
        let mut files = HashMap::new();
        files.insert(
            "test.rs".to_string(),
            "#[allow(dead_code)]\nfn unused() {}\n".to_string(),
        );
        let report = run_all(&files).expect("analysis failed");
        assert!(
            report
                .findings
                .iter()
                .any(|f| f.check == "dead-code-marker"),
            "should detect #[allow(dead_code)]"
        );
    }

    #[test]
    fn todo_detection() {
        let mut files = HashMap::new();
        files.insert(
            "test.py".to_string(),
            "# TODO: fix this later\ndef main():\n    pass\n".to_string(),
        );
        let report = run_all(&files).expect("analysis failed");
        assert!(
            report.findings.iter().any(|f| f.check == "todo-fixme"),
            "should detect TODO comment"
        );
    }

    #[test]
    fn unreachable_detection() {
        let mut files = HashMap::new();
        files.insert(
            "test.rs".to_string(),
            "fn foo() {\n    unreachable!()\n}\n".to_string(),
        );
        let report = run_all(&files).expect("analysis failed");
        assert!(
            report
                .findings
                .iter()
                .any(|f| f.check == "unreachable-marker"),
            "should detect unreachable!()"
        );
    }

    #[test]
    fn duplicate_block_detection() {
        let mut files = HashMap::new();
        let block = "line one\nline two\nline three\nline four\n";
        files.insert("a.rs".to_string(), block.to_string());
        files.insert("b.rs".to_string(), block.to_string());
        let report = run_all(&files).expect("analysis failed");
        assert!(
            !report.duplicate_blocks.is_empty(),
            "should detect duplicate blocks across files"
        );
    }

    #[test]
    fn available_checks_listed() {
        let checks = available_checks();
        assert!(checks.len() >= 7);
        assert!(checks.iter().any(|(name, _)| *name == "dead-code"));
        assert!(checks.iter().any(|(name, _)| *name == "duplicates"));
    }

    #[test]
    fn dead_code_marker_in_string_literal_is_ignored() {
        let mut files = HashMap::new();
        files.insert(
            "test.rs".to_string(),
            "\"#[allow(dead_code)]\";\nlet marker = \"#if 0\";\n".to_string(),
        );
        let report = run_all(&files).expect("analysis failed");
        assert!(
            report
                .findings
                .iter()
                .all(|f| f.check != "dead-code-marker"),
            "string literals should not be reported as dead-code markers"
        );
    }

    #[test]
    fn long_python_function_is_detected_without_braces() {
        let mut files = HashMap::new();
        let mut src = String::from("def heavy():\n");
        for i in 0..70 {
            src.push_str(&format!("    value_{i} = {i}\n"));
        }
        src.push_str("print('done')\n");
        files.insert("sample.py".to_string(), src);

        let findings = run_check(&files, "long-functions").expect("analysis failed");
        assert!(
            findings
                .iter()
                .any(|f| f.check == "long-function" && f.file == "sample.py" && f.line == 1),
            "long python function should be reported"
        );
    }
}
