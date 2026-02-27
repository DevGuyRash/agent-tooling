//! Language-agnostic static analysis for code review workers.
//!
//! All checks are purely text-based (no AST parsing, no external deps).
//! Workers run these on their assigned files to surface mechanical findings
//! before theorem generation, improving signal quality.
#![allow(clippy::implicit_hasher)]
#![allow(clippy::missing_errors_doc)]
#![allow(clippy::must_use_candidate)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_possible_wrap)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::indexing_slicing)]
#![allow(clippy::option_if_let_else)]
#![allow(clippy::format_push_string)]
#![allow(clippy::expect_used)]

use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet, HashMap};

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

/// Typed output for a single `analyze check` invocation.
#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "kebab-case")]
pub enum CheckOutput {
    /// Line-oriented checks that emit standard findings.
    Findings {
        /// Check name supplied by the caller.
        check: String,
        /// Findings emitted by the check.
        findings: Vec<AnalysisFinding>,
    },
    /// Cross-file duplicate text blocks.
    DuplicateBlocks {
        /// Check name supplied by the caller.
        check: String,
        /// Duplicate blocks detected across inputs.
        duplicate_blocks: Vec<DuplicateBlock>,
    },
    /// Functions/blocks with elevated complexity.
    ComplexityHotspots {
        /// Check name supplied by the caller.
        check: String,
        /// Complexity hotspots detected across inputs.
        complexity_hotspots: Vec<ComplexityHotspot>,
    },
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

    let mut file_entries: Vec<(&str, &str)> = files
        .iter()
        .map(|(path, content)| (path.as_str(), content.as_str()))
        .collect();
    file_entries.sort_by(|a, b| a.0.cmp(b.0));

    for (path, content) in file_entries {
        let lines: Vec<&str> = content.lines().collect();
        total_lines += lines.len();
        check_dead_code_markers(&lines, path, &mut findings);
        check_todo_fixme(&lines, path, &mut findings);
        check_long_functions(&lines, path, &mut findings);
        check_long_lines(&lines, path, &mut findings);
        check_unreachable_markers(&lines, path, &mut findings);
    }
    findings.sort_by(|a, b| {
        a.file
            .cmp(&b.file)
            .then_with(|| a.line.cmp(&b.line))
            .then_with(|| a.check.cmp(&b.check))
    });

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
    let output = run_check_output(files, check_name)?;
    Ok(check_output_findings(output))
}

/// Run a single named check and return typed output for the check family.
pub fn run_check_output(
    files: &HashMap<String, String>,
    check_name: &str,
) -> anyhow::Result<CheckOutput> {
    match check_name {
        "duplicates" => Ok(CheckOutput::DuplicateBlocks {
            check: check_name.to_string(),
            duplicate_blocks: find_duplicate_blocks(files),
        }),
        "complexity" => Ok(CheckOutput::ComplexityHotspots {
            check: check_name.to_string(),
            complexity_hotspots: find_complexity_hotspots(files),
        }),
        _ => Ok(CheckOutput::Findings {
            check: check_name.to_string(),
            findings: run_line_check(files, check_name)?,
        }),
    }
}

fn run_line_check(
    files: &HashMap<String, String>,
    check_name: &str,
) -> anyhow::Result<Vec<AnalysisFinding>> {
    let mut findings = Vec::new();
    let mut file_entries: Vec<(&str, &str)> = files
        .iter()
        .map(|(path, content)| (path.as_str(), content.as_str()))
        .collect();
    file_entries.sort_by(|a, b| a.0.cmp(b.0));

    for (path, content) in file_entries {
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
    findings.sort_by(|a, b| {
        a.file
            .cmp(&b.file)
            .then_with(|| a.line.cmp(&b.line))
            .then_with(|| a.check.cmp(&b.check))
    });
    Ok(findings)
}

fn check_output_findings(output: CheckOutput) -> Vec<AnalysisFinding> {
    match output {
        CheckOutput::Findings { findings, .. } => findings,
        CheckOutput::DuplicateBlocks {
            duplicate_blocks, ..
        } => {
            let mut findings = Vec::new();
            for block in duplicate_blocks {
                let location_count = block.locations.len();
                let excerpt = format!(
                    "duplicate block {} ({} lines, {} locations)",
                    block.fingerprint, block.line_count, location_count
                );
                let detail = format!(
                    "Duplicate block appears in {location_count} locations (fingerprint {})",
                    block.fingerprint
                );
                for location in block.locations {
                    findings.push(AnalysisFinding {
                        check: "duplicates".to_string(),
                        file: location.file,
                        line: location.start_line,
                        excerpt: excerpt.clone(),
                        detail: detail.clone(),
                    });
                }
            }
            findings
        }
        CheckOutput::ComplexityHotspots {
            complexity_hotspots,
            ..
        } => complexity_hotspots
            .into_iter()
            .map(|spot| AnalysisFinding {
                check: "complexity".to_string(),
                file: spot.file,
                line: spot.start_line,
                excerpt: format!(
                    "{} (nesting={}, branches={})",
                    spot.name_hint, spot.max_nesting, spot.branch_count
                ),
                detail: format!(
                    "Complexity hotspot: nesting={}, branches={}",
                    spot.max_nesting, spot.branch_count
                ),
            })
            .collect(),
    }
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
                if is_marker_inside_quotes(&lower_line, &marker_lower) {
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
    let mut func_start: Option<(usize, String)> = None;
    let mut brace_depth: i32 = 0;
    let mut indent_start: Option<usize> = None;
    let mut saw_open_brace = false;

    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if should_skip_line_for_function_analysis(line) {
            continue;
        }

        if let Some((start, ref name)) = func_start {
            let func_len = idx + 1 - start;
            let at_dedent = !saw_open_brace
                && indent_start.is_some_and(|is| {
                    let current_indent = line.len() - line.trim_start().len();
                    current_indent <= is && !trimmed.is_empty()
                });
            if at_dedent {
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

        let is_fn_start = is_function_start(line, FUNCTION_START_PATTERNS);

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
            let at_brace_end = saw_open_brace && brace_depth <= 0;

            if at_brace_end {
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
    let mut first_overflow_line: Option<usize> = None;
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
            } else if first_overflow_line.is_none() {
                first_overflow_line = Some(idx + 1);
            }
        }
    }
    if count > 5 {
        let overflow_line = first_overflow_line.map_or(1, |line| line);
        out.push(AnalysisFinding {
            check: "long-line".to_string(),
            file: path.to_string(),
            line: overflow_line,
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
                if is_marker_inside_quotes(&lower_line, &marker.to_ascii_lowercase()) {
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

/// Find duplicate text blocks (≥4 consecutive lines) across files.
pub fn find_duplicate_blocks(files: &HashMap<String, String>) -> Vec<DuplicateBlock> {
    let min_block = 4;
    let mut fingerprints: BTreeMap<u64, Vec<DuplicateLocation>> = BTreeMap::new();

    let mut file_entries: Vec<(&str, &str)> = files
        .iter()
        .map(|(path, content)| (path.as_str(), content.as_str()))
        .collect();
    file_entries.sort_by(|a, b| a.0.cmp(b.0));

    for (path, content) in file_entries {
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
            let hash = simple_hash(&block.join("\n"));
            fingerprints
                .entry(hash)
                .or_default()
                .push(DuplicateLocation {
                    file: path.to_string(),
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
        let unique_files: BTreeSet<&str> = deduped.iter().map(|l| l.file.as_str()).collect();
        if unique_files.len() >= 2 {
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
    duplicates.sort_by(|a, b| {
        b.locations
            .len()
            .cmp(&a.locations.len())
            .then_with(|| a.fingerprint.cmp(&b.fingerprint))
    });
    duplicates.truncate(20);
    duplicates
}

/// Identify functions/blocks with high nesting depth or high branch count.
pub fn find_complexity_hotspots(files: &HashMap<String, String>) -> Vec<ComplexityHotspot> {
    let mut hotspots = Vec::new();

    let mut file_entries: Vec<(&str, &str)> = files
        .iter()
        .map(|(path, content)| (path.as_str(), content.as_str()))
        .collect();
    file_entries.sort_by(|a, b| a.0.cmp(b.0));

    for (path, content) in file_entries {
        let lines: Vec<&str> = content.lines().collect();
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
            if should_skip_line_for_function_analysis(line) {
                continue;
            }

            let is_fn = is_function_start(line, FUNCTION_START_PATTERNS);

            if is_fn {
                if let Some((start, ref name)) = func_start {
                    if max_nesting > 4 || branch_count > 10 {
                        hotspots.push(ComplexityHotspot {
                            file: path.to_string(),
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
                    file: path.to_string(),
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
            .then_with(|| a.file.cmp(&b.file))
            .then_with(|| a.start_line.cmp(&b.start_line))
            .then_with(|| a.name_hint.cmp(&b.name_hint))
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

const FUNCTION_START_PATTERNS: &[&str] = &["fn ", "def ", "func ", "function ", "sub ", "method "];

fn should_skip_line_for_function_analysis(line: &str) -> bool {
    let trimmed = line.trim();
    trimmed.is_empty()
        || trimmed.starts_with("//")
        || trimmed.starts_with('#')
        || is_probable_string_literal_line(line)
}

fn is_function_start(line: &str, fn_patterns: &[&str]) -> bool {
    let trimmed = line.trim();
    let lower_line = trimmed.to_ascii_lowercase();
    let inline_fn_syntax = lower_line.contains("fn ")
        && (trimmed.contains('(') || trimmed.contains('{'))
        && !is_marker_inside_quotes(&lower_line, "fn ");
    let callable_modifier_start = is_callable_modifier_declaration(&lower_line);

    fn_patterns.iter().any(|p| lower_line.starts_with(p))
        || callable_modifier_start
        || inline_fn_syntax
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
        || trimmed.starts_with('\'')
        || trimmed.starts_with("r\"")
        || trimmed.starts_with("r#\"")
        || trimmed.starts_with("b\"")
        || trimmed.starts_with("b'")
        || trimmed.starts_with("f\"")
        || trimmed.starts_with("f'")
        || trimmed.starts_with("u\"")
        || trimmed.starts_with("u'")
        || trimmed.starts_with("'''")
        || trimmed.starts_with("\"\"\"")
}

fn is_marker_inside_quotes(line: &str, marker: &str) -> bool {
    if marker.is_empty() || !line.contains(marker) {
        return false;
    }

    let mut in_quote: Option<char> = None;
    let mut escaped = false;
    let mut saw_quoted_marker = false;

    for (idx, ch) in line.char_indices() {
        if in_quote.is_none() && line[idx..].starts_with(marker) {
            return false;
        }
        if in_quote.is_some() && line[idx..].starts_with(marker) {
            saw_quoted_marker = true;
        }

        if ch == '\\' {
            escaped = in_quote.is_some() && !escaped;
            continue;
        }

        if let Some(quote_char) = in_quote {
            if ch == quote_char && !escaped {
                in_quote = None;
            }
        } else if (ch == '"' || ch == '\'') && !escaped {
            in_quote = Some(ch);
        }

        escaped = false;
    }

    saw_quoted_marker
}

fn is_callable_modifier_declaration(lower_line: &str) -> bool {
    const MODIFIER_PREFIXES: &[&str] = &["public ", "private ", "protected ", "static "];
    const NON_CALLABLE_TOKENS: &[&str] = &[" class ", " interface ", " enum ", " struct "];

    if !MODIFIER_PREFIXES
        .iter()
        .any(|prefix| lower_line.starts_with(prefix))
    {
        return false;
    }
    if !lower_line.contains('(') || lower_line.ends_with(';') {
        return false;
    }

    !NON_CALLABLE_TOKENS
        .iter()
        .any(|token| lower_line.contains(token))
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
    fn duplicate_blocks_require_distinct_files() {
        let mut files = HashMap::new();
        files.insert(
            "solo.rs".to_string(),
            [
                "line one",
                "line two",
                "line three",
                "line four",
                "line one",
                "line two",
                "line three",
                "line four",
            ]
            .join("\n"),
        );

        let report = run_all(&files).expect("analysis failed");
        assert!(
            report.duplicate_blocks.is_empty(),
            "duplicate blocks must require at least two distinct files"
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
    fn dead_code_marker_in_single_quoted_literal_is_ignored() {
        let mut files = HashMap::new();
        files.insert(
            "test.js".to_string(),
            "const marker = '#if 0';\nconst dead = '#[allow(dead_code)]';\n".to_string(),
        );
        let report = run_all(&files).expect("analysis failed");
        assert!(
            report
                .findings
                .iter()
                .all(|f| f.check != "dead-code-marker"),
            "single-quoted literals should not be reported as dead-code markers"
        );
    }

    #[test]
    fn unreachable_marker_in_single_quoted_literal_is_ignored() {
        let mut files = HashMap::new();
        files.insert(
            "test.js".to_string(),
            "const msg = 'todo!()';\nconst panic_text = 'panic!(\"boom\")';\n".to_string(),
        );
        let report = run_all(&files).expect("analysis failed");
        assert!(
            report
                .findings
                .iter()
                .all(|f| f.check != "unreachable-marker"),
            "single-quoted literals should not be reported as unreachable markers"
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

    #[test]
    fn long_python_function_at_threshold_is_not_reported_on_dedent() {
        let mut files = HashMap::new();
        let mut src = String::from("def exact_threshold():\n");
        for i in 0..59 {
            src.push_str(&format!("    value_{i} = {i}\n"));
        }
        src.push_str("print('outside')\n");
        files.insert("sample.py".to_string(), src);

        let findings = run_check(&files, "long-functions").expect("analysis failed");
        assert!(
            findings.is_empty(),
            "exact-threshold function should not be reported"
        );
    }

    #[test]
    fn long_function_detection_ignores_function_like_strings() {
        let mut files = HashMap::new();
        let mut src = String::from("println!(\"this is a function: fn foo() {\");\n");
        for i in 0..70 {
            src.push_str(&format!("let value_{i} = {i};\n"));
        }
        files.insert("sample.rs".to_string(), src);

        let findings = run_check(&files, "long-functions").expect("analysis failed");
        assert!(
            findings.is_empty(),
            "function-like strings should not start long-function spans"
        );
    }

    #[test]
    fn long_function_detection_ignores_function_like_python_triple_quotes() {
        let mut files = HashMap::new();
        let mut src = String::from("\"\"\"def fake():\n");
        for i in 0..70 {
            src.push_str(&format!("line_{i}\n"));
        }
        src.push_str("\"\"\"\n");
        files.insert("sample.py".to_string(), src);

        let findings = run_check(&files, "long-functions").expect("analysis failed");
        assert!(
            findings.is_empty(),
            "triple-quoted string content should not start long-function spans"
        );
    }

    #[test]
    fn run_check_output_returns_duplicates_variant() {
        let mut files = HashMap::new();
        let block = "line one\nline two\nline three\nline four\n";
        files.insert("a.rs".to_string(), block.to_string());
        files.insert("b.rs".to_string(), block.to_string());

        let output = run_check_output(&files, "duplicates").expect("analysis failed");
        assert!(
            matches!(output, CheckOutput::DuplicateBlocks { .. }),
            "expected duplicate blocks output"
        );
        if let CheckOutput::DuplicateBlocks {
            check,
            duplicate_blocks,
        } = output
        {
            assert_eq!(check, "duplicates");
            assert!(
                !duplicate_blocks.is_empty(),
                "should detect duplicate blocks"
            );
        }
    }

    #[test]
    fn run_check_supports_duplicates_with_blank_lines() {
        let mut files = HashMap::new();
        let block = "line one\nline two\n\nline four\n";
        files.insert("a.rs".to_string(), block.to_string());
        files.insert("b.rs".to_string(), block.to_string());

        let findings = run_check(&files, "duplicates").expect("analysis failed");
        assert!(
            findings.iter().any(|f| f.check == "duplicates"),
            "expected flattened duplicate findings"
        );
        assert!(
            findings
                .iter()
                .any(|f| f.file == "a.rs" || f.file == "b.rs"),
            "expected duplicate findings to point at duplicate file locations"
        );
    }

    #[test]
    fn long_function_detection_handles_new_function_on_dedent_line() {
        let mut files = HashMap::new();
        let mut src = String::from("def first():\n    x = 1\ndef second():\n");
        for i in 0..70 {
            src.push_str(&format!("    value_{i} = {i}\n"));
        }
        files.insert("sample.py".to_string(), src);

        let findings = run_check(&files, "long-functions").expect("analysis failed");
        assert!(
            findings
                .iter()
                .any(|f| f.file == "sample.py" && f.line == 3 && f.check == "long-function"),
            "expected second function to be analyzed after dedent transition"
        );
    }

    #[test]
    fn single_line_function_closes_before_skipped_lines() {
        let mut files = HashMap::new();
        let mut src = String::from("fn noop() {}\n");
        for _ in 0..80 {
            src.push_str("// trailing comment\n");
        }
        files.insert("sample.rs".to_string(), src);

        let findings = run_check(&files, "long-functions").expect("analysis failed");
        assert!(
            findings.is_empty(),
            "single-line function should not stay active across skipped lines"
        );
    }

    #[test]
    fn run_check_supports_complexity_for_pub_async_fn() {
        let mut files = HashMap::new();
        let mut src = String::from("pub async fn hot_path() {\n");
        for i in 0..12 {
            src.push_str(&format!("    if cond_{i} {{\n        work();\n    }}\n"));
        }
        src.push_str("}\n");
        files.insert("sample.rs".to_string(), src);

        let findings = run_check(&files, "complexity").expect("analysis failed");
        assert!(
            findings
                .iter()
                .any(|f| { f.file == "sample.rs" && f.check == "complexity" && f.line == 1 }),
            "expected complexity hotspot findings from run_check"
        );
    }

    #[test]
    fn marker_detection_handles_mixed_quoted_and_unquoted_occurrences() {
        let mut files = HashMap::new();
        files.insert(
            "sample.rs".to_string(),
            "let s = \"todo!()\";\nfn main() { todo!(); }\n".to_string(),
        );

        let report = run_all(&files).expect("analysis failed");
        assert!(
            report
                .findings
                .iter()
                .any(|f| f.check == "unreachable-marker" && f.line == 2),
            "unquoted marker should still be detected when quoted marker appears elsewhere"
        );
    }

    #[test]
    fn marker_detection_handles_single_quoted_and_unquoted_occurrences() {
        let mut files = HashMap::new();
        files.insert(
            "sample.js".to_string(),
            "const s = 'todo!()';\nfunction main() { todo!(); }\n".to_string(),
        );

        let report = run_all(&files).expect("analysis failed");
        assert!(
            report
                .findings
                .iter()
                .any(|f| f.check == "unreachable-marker" && f.line == 2),
            "unquoted marker should still be detected when single-quoted marker appears elsewhere"
        );
    }

    #[test]
    fn function_start_detection_ignores_non_callable_modifier_lines() {
        assert!(!is_function_start(
            "public class Foo {",
            FUNCTION_START_PATTERNS
        ));
        assert!(!is_function_start(
            "private int value;",
            FUNCTION_START_PATTERNS
        ));
        assert!(!is_function_start(
            "protected string name;",
            FUNCTION_START_PATTERNS
        ));
    }

    #[test]
    fn function_start_detection_accepts_callable_modifier_lines() {
        assert!(is_function_start(
            "public void run() {",
            FUNCTION_START_PATTERNS
        ));
        assert!(is_function_start(
            "private static int calc(int x) {",
            FUNCTION_START_PATTERNS
        ));
        assert!(is_function_start(
            "protected Task ExecuteAsync() {",
            FUNCTION_START_PATTERNS
        ));
    }

    #[test]
    fn long_line_overflow_summary_uses_positive_line_number() {
        let mut files = HashMap::new();
        let mut src = String::new();
        for _ in 0..6 {
            src.push('x');
            src.push_str(&"y".repeat(130));
            src.push('\n');
        }
        files.insert("sample.txt".to_string(), src);

        let findings = run_check(&files, "long-lines").expect("analysis failed");
        let overflow = findings
            .iter()
            .find(|f| f.detail.contains("showing first 5"))
            .expect("overflow summary missing");
        assert_eq!(overflow.line, 6);
    }

    #[test]
    fn run_all_output_order_is_deterministic_across_insertion_orders() {
        let a_src = "fn a() {\n    // TODO: alpha\n    unreachable!();\n}\n";
        let b_src = "fn b() {\n    // TODO: beta\n    panic!(\"boom\");\n}\n";

        let mut files_ab = HashMap::new();
        files_ab.insert("a.rs".to_string(), a_src.to_string());
        files_ab.insert("b.rs".to_string(), b_src.to_string());

        let mut files_ba = HashMap::new();
        files_ba.insert("b.rs".to_string(), b_src.to_string());
        files_ba.insert("a.rs".to_string(), a_src.to_string());

        let report_ab = run_all(&files_ab).expect("analysis failed");
        let report_ba = run_all(&files_ba).expect("analysis failed");

        let findings_ab = serde_json::to_string(&report_ab.findings).expect("serialize findings");
        let findings_ba = serde_json::to_string(&report_ba.findings).expect("serialize findings");
        assert_eq!(
            findings_ab, findings_ba,
            "findings ordering should be stable"
        );

        let dead_ab =
            serde_json::to_string(&report_ab.dead_markers).expect("serialize dead markers");
        let dead_ba =
            serde_json::to_string(&report_ba.dead_markers).expect("serialize dead markers");
        assert_eq!(dead_ab, dead_ba, "dead_markers ordering should be stable");
    }
}
