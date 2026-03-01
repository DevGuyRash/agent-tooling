//! Surface-level compliance tests for the `code-review` skill package.

use anyhow::{ensure, Context};
use std::collections::BTreeSet;
use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const FALLBACK_DOCS: &[&str] = &[
    "references/reviewer-fallback.md",
    "references/applicator-fallback.md",
    "references/orchestrator-fallback.md",
    "references/fullcycle-fallback.md",
];

const PROTOCOL_FILES: &[&str] = &[
    "scripts/mpcr-src/protocols/reviewer.toml",
    "scripts/mpcr-src/protocols/applicator.toml",
    "scripts/mpcr-src/protocols/orchestrator.toml",
    "scripts/mpcr-src/protocols/dispatch.toml",
    "scripts/mpcr-src/protocols/session.toml",
    "scripts/mpcr-src/protocols/templates.toml",
];

const BANNED_AMBIGUITY: &[(&str, &str)] = &[
    ("non-", "trivial"),
    ("as ", "needed"),
    ("if ", "feasible"),
    ("et", "c."),
];

fn skill_root() -> anyhow::Result<PathBuf> {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| anyhow::anyhow!("failed to resolve skill root from {}", manifest.display()))
}

fn collect_files(dir: &Path, out: &mut Vec<PathBuf>) -> anyhow::Result<()> {
    for entry in fs::read_dir(dir).with_context(|| format!("read_dir {}", dir.display()))? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            if path.file_name() == Some(OsStr::new("target")) {
                continue;
            }
            collect_files(&path, out)?;
            continue;
        }
        out.push(path);
    }
    Ok(())
}

fn normalize(text: &str) -> String {
    text.replace("\r\n", "\n").trim_end().to_string()
}

fn read_rel(root: &Path, rel: &str) -> anyhow::Result<String> {
    fs::read_to_string(root.join(rel)).with_context(|| format!("read {}", root.join(rel).display()))
}

fn is_normative_line(line: &str) -> bool {
    let trimmed = line.trim();
    if trimmed.is_empty()
        || trimmed.starts_with('#')
        || trimmed.starts_with('|')
        || trimmed.starts_with("```")
        || trimmed.starts_with("---")
        || trimmed.starts_with("name:")
        || trimmed.starts_with("description:")
        || trimmed.starts_with("compatibility:")
    {
        return false;
    }

    let stripped = trimmed
        .trim_start_matches(|c: char| c == '-' || c == '*' || c == ' ')
        .trim_start_matches(|c: char| c.is_ascii_digit() || c == '.' || c == ')' || c == ' ');

    stripped.starts_with("You ")
        || stripped.starts_with("IF ")
        || stripped.starts_with("WHEN ")
        || stripped.starts_with("Forbidden:")
}

fn line_uses_ears(line: &str) -> bool {
    let trimmed = line.trim();
    let stripped = trimmed
        .trim_start_matches(|c: char| c == '-' || c == '*' || c == ' ')
        .trim_start_matches(|c: char| c.is_ascii_digit() || c == '.' || c == ')' || c == ' ');

    stripped.starts_with("IF ")
        || stripped.starts_with("WHEN ")
        || stripped.starts_with("Forbidden:")
        || stripped.starts_with("You are ")
        || stripped.contains(" SHALL ")
        || stripped.contains(" SHALL NOT ")
        || stripped.contains(" MAY ")
        || stripped.contains(" MUST ")
        || stripped.starts_with("You SHALL")
        || stripped.starts_with("You SHALL NOT")
        || stripped.starts_with("You MAY")
        || stripped.starts_with("You MUST")
}

fn extract_doc_commands(text: &str) -> BTreeSet<String> {
    let mut commands = BTreeSet::new();
    for segment in text.split('`') {
        for line in segment.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("mpcr ") {
                commands.insert(trimmed.trim_end_matches('\\').trim().to_string());
            }
        }
    }
    commands
}

fn validate_doc_command(bin: &str, command: &str) -> anyhow::Result<()> {
    let tokens: Vec<&str> = command.split_whitespace().collect();
    ensure!(!tokens.is_empty(), "empty command extracted");
    ensure!(
        tokens[0] == "mpcr",
        "unexpected non-mpcr command: {command}"
    );

    let is_placeholder = |t: &str| {
        t.contains('<')
            || t.contains('[')
            || t.contains("...")
            || t.contains('*')
            || t == "|"
            || t.contains('|')
    };
    let has_placeholders = tokens.iter().any(|t| is_placeholder(t)) || command.contains("<<");

    let args: Vec<String> = if tokens.len() >= 3 && tokens[1] == "protocol" && !has_placeholders {
        tokens[1..].iter().map(|s| (*s).to_string()).collect()
    } else if tokens.len() >= 3 && tokens[1] == "analyze" && tokens[2] == "list-checks" {
        vec!["analyze".into(), "list-checks".into(), "--json".into()]
    } else {
        let prefix: Vec<&str> = tokens[1..]
            .iter()
            .copied()
            .take_while(|t| !is_placeholder(t))
            .collect();
        if prefix.len() >= 2 {
            vec![prefix[0].into(), prefix[1].into(), "--help".into()]
        } else {
            vec![tokens[1].into(), "--help".into()]
        }
    };

    let output = Command::new(bin)
        .args(&args)
        .output()
        .with_context(|| format!("run {}", args.join(" ")))?;
    ensure!(
        output.status.success(),
        "documented command shape failed for `{command}` via `{}`: {}",
        args.join(" "),
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(())
}

#[test]
fn skill_text_files_use_lf_line_endings() -> anyhow::Result<()> {
    let root = skill_root()?;
    let mut files = Vec::new();
    collect_files(&root, &mut files)?;

    let text_exts = ["md", "toml", "rs", "sh", "ps1", "cmd"];
    for path in files {
        let ext = path.extension().and_then(OsStr::to_str).unwrap_or_default();
        if !text_exts.contains(&ext) && path.file_name() != Some(OsStr::new("mpcr")) {
            continue;
        }
        let bytes = fs::read(&path).with_context(|| format!("read {}", path.display()))?;
        ensure!(
            !bytes.windows(2).any(|w| w == b"\r\n"),
            "found CRLF line endings in {}",
            path.display()
        );
    }
    Ok(())
}

#[test]
fn skill_router_and_fallbacks_preserve_progressive_disclosure() -> anyhow::Result<()> {
    let root = skill_root()?;
    let skill_md = read_rel(&root, "SKILL.md")?;
    ensure!(skill_md.contains("<skills-file-root>"));
    ensure!(skill_md.contains("/tmp/skill-errors/"));
    ensure!(skill_md.contains("%TEMP%"));
    ensure!(skill_md.contains("_code-review_errors.md"));
    ensure!(
        skill_md.lines().count() <= 120,
        "SKILL.md should stay router-sized"
    );
    ensure!(!skill_md.contains("reviewer-protocol.md"));
    ensure!(!skill_md.contains("applicator-protocol.md"));

    for rel in FALLBACK_DOCS {
        let text = read_rel(&root, rel)?;
        ensure!(text.lines().count() <= 300, "{rel} exceeded 300 lines");
        ensure!(
            !text.contains("references/"),
            "{rel} should not chain to nested references"
        );
    }
    Ok(())
}

#[test]
fn canonical_only_artifacts_and_language_remain() -> anyhow::Result<()> {
    let root = skill_root()?;
    ensure!(!root.join("references/reviewer-protocol.md").exists());
    ensure!(!root.join("references/applicator-protocol.md").exists());

    let mut files: Vec<PathBuf> = vec![
        root.join("SKILL.md"),
        root.join("scripts/mpcr-src/src/protocol.rs"),
    ];
    for rel in FALLBACK_DOCS.iter().chain(PROTOCOL_FILES.iter()) {
        files.push(root.join(rel));
    }

    for path in files {
        let text = fs::read_to_string(&path)
            .with_context(|| format!("read canonical artifact {}", path.display()))?;
        let lower = text.to_ascii_lowercase();
        let banned_term = ["lega", "cy"].concat();
        let pointer_label = ["Compatibility", " Pointer"].concat();
        ensure!(
            !lower.contains(&banned_term),
            "non-canonical wording remains in {}",
            path.display()
        );
        ensure!(
            !text.contains(&pointer_label),
            "pointer artifact remains in {}",
            path.display()
        );
    }
    Ok(())
}

#[test]
fn normative_docs_follow_ears_and_avoid_banned_ambiguity() -> anyhow::Result<()> {
    let root = skill_root()?;
    let mut docs = vec![("SKILL.md".to_string(), read_rel(&root, "SKILL.md")?)];
    for rel in FALLBACK_DOCS.iter().chain(PROTOCOL_FILES.iter()) {
        docs.push(((*rel).to_string(), read_rel(&root, rel)?));
    }

    for (rel, text) in docs {
        let lower = text.to_ascii_lowercase();
        for (a, b) in BANNED_AMBIGUITY {
            let phrase = format!("{a}{b}");
            ensure!(
                !lower.contains(&phrase),
                "banned ambiguous phrase `{phrase}` found in {rel}"
            );
        }

        for (idx, line) in text.lines().enumerate() {
            if is_normative_line(line) {
                ensure!(
                    line_uses_ears(line),
                    "non-EARS normative line in {rel}:{} -> {}",
                    idx + 1,
                    line.trim()
                );
            }
        }
    }
    Ok(())
}

#[test]
fn fallback_docs_match_protocol_renderers() -> anyhow::Result<()> {
    let root = skill_root()?;
    let references = root.join("references");

    let reviewer_file = fs::read_to_string(references.join("reviewer-fallback.md"))?;
    let applicator_file = fs::read_to_string(references.join("applicator-fallback.md"))?;
    let orchestrator_file = fs::read_to_string(references.join("orchestrator-fallback.md"))?;
    let fullcycle_file = fs::read_to_string(references.join("fullcycle-fallback.md"))?;

    let reviewer_expected = mpcr::protocol::reviewer_fallback_doc()?;
    let applicator_expected = mpcr::protocol::applicator_fallback_doc()?;
    let orchestrator_expected = mpcr::protocol::orchestrator_fallback_doc()?;
    let fullcycle_expected = mpcr::protocol::fullcycle_fallback_doc()?;

    ensure!(
        normalize(&reviewer_file) == normalize(&reviewer_expected),
        "reviewer fallback doc is out of sync"
    );
    ensure!(
        normalize(&applicator_file) == normalize(&applicator_expected),
        "applicator fallback doc is out of sync"
    );
    ensure!(
        normalize(&orchestrator_file) == normalize(&orchestrator_expected),
        "orchestrator fallback doc is out of sync"
    );
    ensure!(
        normalize(&fullcycle_file) == normalize(&fullcycle_expected),
        "fullcycle fallback doc is out of sync"
    );
    Ok(())
}

#[test]
fn documented_mpcr_commands_resolve_against_current_cli() -> anyhow::Result<()> {
    let root = skill_root()?;
    let mut commands = BTreeSet::new();
    for rel in ["SKILL.md"]
        .into_iter()
        .chain(FALLBACK_DOCS.iter().copied())
    {
        commands.extend(extract_doc_commands(&read_rel(&root, rel)?));
    }

    let bin = env!("CARGO_BIN_EXE_mpcr");
    for command in commands {
        validate_doc_command(bin, &command)?;
    }
    Ok(())
}
