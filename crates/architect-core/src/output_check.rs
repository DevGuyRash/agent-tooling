//! Markdown output contract validator for deterministic skill responses.

use std::collections::BTreeMap;

use regex::Regex;
use serde_yaml::Value as YamlValue;

use crate::error::AppError;
use crate::fetch::normalize_image_reference;
use crate::heuristics::service_uses_writable_named_volume;
use crate::knowledge::researched_config_for_image;
use crate::model::RuntimeSignatures;
use crate::yaml_merge::{materialize_yaml_merge_keys, MAX_YAML_MERGE_DEPTH};

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct OutputCheckResult {
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

/// Validate markdown content against required section order and traceability IDs.
///
/// # Arguments
/// * `content` - Markdown payload to validate.
/// * `mode` - Workflow mode, `compose` or `image`.
///
/// # Returns
/// * `Ok(OutputCheckResult)` with validation errors and warnings; empty `errors` means pass.
/// * `Err(AppError)` when mode is unsupported.
pub fn validate_output_contract(content: &str, mode: &str) -> Result<OutputCheckResult, AppError> {
    let headings = collect_headings(content);
    let swarm_requires_ownership_bootstrap =
        mode == "swarm" && swarm_ownership_bootstrap_required(content, &headings);

    let mut required_sections = match mode {
        "compose" => vec![
            "Requirements",
            "Mode Applicability Matrix",
            "Image Research",
            "Unknown Unknowns",
            "Deployment Overview",
            "Architecture Plan",
            "Visualization",
            "Task List",
            "Directory/Prerequisites",
            "Configuration Files",
            "Operational Guide",
        ],
        "swarm" => vec![
            "Requirements",
            "Mode Applicability Matrix",
            "Image Research",
            "Unknown Unknowns",
            "Stack Overview",
            "Architecture Plan",
            "Visualization",
            "Task List",
            "Directory/Prerequisites",
            "Configuration Files",
            "Operational Guide",
        ],
        "image" => vec![
            "Requirements",
            "Mode Applicability Matrix",
            "Image Research",
            "Unknown Unknowns",
            "Build Overview",
            "Build Design Plan",
            "Visualization",
            "Task List",
            "Project Layout/Prerequisites",
            "Generated Files",
            "Operational Guide",
        ],
        _ => {
            return Err(AppError::InvalidInput {
                reason: format!("unsupported output-check mode: {mode}"),
            });
        }
    };

    if swarm_requires_ownership_bootstrap {
        required_sections.insert(required_sections.len() - 1, "Ownership Bootstrap");
    }

    let mut result = OutputCheckResult::default();

    let mut previous_index = None;
    for section in &required_sections {
        let current_index = headings
            .iter()
            .position(|(_, heading)| heading.eq_ignore_ascii_case(section));
        match current_index {
            Some(position) => {
                if previous_index.is_some_and(|prior| position < prior) {
                    result
                        .errors
                        .push(format!("section out of order: {section}"));
                }
                previous_index = Some(position);
            }
            None => {
                result
                    .errors
                    .push(format!("missing required section: {section}"));
            }
        }
    }

    let marker_re =
        Regex::new(r"\b(?:AC|IMG|RSK|O)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b").map_err(|error| {
            AppError::InvalidInput {
                reason: format!("failed to compile marker regex: {error}"),
            }
        })?;

    for section in &required_sections {
        if let Some((start, end)) = section_bounds(&headings, section, content.lines().count()) {
            let section_text = extract_line_span(content, start, end);
            if !marker_re.is_match(&section_text) {
                result
                    .errors
                    .push(format!("missing traceability marker in section: {section}"));
            }
        }
    }

    for marker in ["AC-", "IMG-", "RSK-", "O-"] {
        if !content.contains(marker) {
            result
                .errors
                .push(format!("missing marker family: {marker}*"));
        }
    }

    if mode == "image" {
        let lower = content.to_ascii_lowercase();
        if !lower.contains("docker-bake.hcl") {
            result
                .errors
                .push("missing required image artifact reference: docker-bake.hcl".to_string());
        }
        if !lower.contains("docker buildx bake") {
            result.errors.push(
                "missing required image release instructions: bake/buildx guidance".to_string(),
            );
        }
        if !lower.contains("cosign sign") {
            result
                .errors
                .push("missing required image release instructions: signing guidance".to_string());
        }
        if !lower.contains("--attest type=sbom") {
            result.errors.push(
                "missing required image release instructions: sbom attestation guidance"
                    .to_string(),
            );
        }
        if !lower.contains("--attest type=provenance,mode=max") {
            result.errors.push(
                "missing required image release instructions: provenance attestation guidance"
                    .to_string(),
            );
        }
    }

    if mode == "compose" || mode == "swarm" {
        let lower = content.to_ascii_lowercase();
        if lower.contains("skipped") && !lower.contains("residual risk") {
            result.errors.push(
                "skipped validation steps must include a residual risk statement".to_string(),
            );
        }
    }

    Ok(result)
}

fn collect_headings(content: &str) -> Vec<(usize, String)> {
    let mut headings = Vec::new();
    let mut fence_state = FenceState::Outside;
    for (index, line) in content.lines().enumerate() {
        let trimmed = line.trim();
        if let Some(state) = update_fence_state(fence_state, trimmed) {
            fence_state = state;
            continue;
        }

        if fence_state == FenceState::Outside && trimmed.starts_with("# ") {
            let value = trimmed.trim_start_matches("# ").trim().to_string();
            if !value.is_empty() {
                headings.push((index + 1, value));
            }
        }
    }
    headings
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FenceState {
    Outside,
    Backtick,
    Tilde,
}

fn update_fence_state(current: FenceState, line: &str) -> Option<FenceState> {
    if line.starts_with("```") {
        return match current {
            FenceState::Outside => Some(FenceState::Backtick),
            FenceState::Backtick => Some(FenceState::Outside),
            FenceState::Tilde => None,
        };
    }

    if line.starts_with("~~~") {
        return match current {
            FenceState::Outside => Some(FenceState::Tilde),
            FenceState::Tilde => Some(FenceState::Outside),
            FenceState::Backtick => None,
        };
    }

    None
}

fn section_bounds(
    headings: &[(usize, String)],
    section: &str,
    total_lines: usize,
) -> Option<(usize, usize)> {
    let mut start = None;
    let mut end = None;
    for (index, (line_no, heading)) in headings.iter().enumerate() {
        if heading.eq_ignore_ascii_case(section) {
            start = Some(*line_no);
            end = headings
                .get(index + 1)
                .map(|(line, _)| *line)
                .or(Some(total_lines + 1));
            break;
        }
    }
    match (start, end) {
        (Some(begin), Some(finish)) if begin < finish => Some((begin, finish)),
        _ => None,
    }
}

fn extract_line_span(content: &str, start: usize, end: usize) -> String {
    content
        .lines()
        .enumerate()
        .filter(|(index, _)| {
            let line_no = index + 1;
            line_no >= start && line_no < end
        })
        .map(|(_, line)| line)
        .collect::<Vec<&str>>()
        .join("\n")
}

fn swarm_ownership_bootstrap_required(content: &str, headings: &[(usize, String)]) -> bool {
    let image_runtime_users = collect_image_runtime_users(content, headings);
    let Some((start, end)) =
        section_bounds(headings, "Configuration Files", content.lines().count())
    else {
        return false;
    };

    let section_text = extract_line_span(content, start, end);
    for block in fenced_code_blocks(&section_text) {
        let Ok(mut parsed) = serde_yaml::from_str::<YamlValue>(&block) else {
            continue;
        };
        if materialize_yaml_merge_keys(&mut parsed, MAX_YAML_MERGE_DEPTH).is_err() {
            continue;
        }
        if yaml_requires_swarm_ownership_bootstrap(&parsed, &image_runtime_users) {
            return true;
        }
    }

    false
}

fn collect_image_runtime_users(
    content: &str,
    headings: &[(usize, String)],
) -> BTreeMap<String, String> {
    let Some((start, end)) = section_bounds(headings, "Image Research", content.lines().count())
    else {
        return BTreeMap::new();
    };

    let section_text = extract_line_span(content, start, end);
    let mut runtime_users = BTreeMap::new();

    for block in fenced_code_blocks(&section_text) {
        let Ok(mut document) = serde_yaml::from_str::<YamlValue>(&block) else {
            continue;
        };
        if materialize_yaml_merge_keys(&mut document, MAX_YAML_MERGE_DEPTH).is_err() {
            continue;
        }
        if let Some((normalized, runtime_user)) = image_runtime_user_from_yaml(&document) {
            runtime_users.insert(normalized, runtime_user);
        }
    }

    for line in non_fenced_lines(&section_text) {
        if let Some((normalized, runtime_user)) = image_runtime_user_from_line(&line) {
            runtime_users.entry(normalized).or_insert(runtime_user);
        }
    }

    runtime_users
}

fn fenced_code_blocks(content: &str) -> Vec<String> {
    let mut blocks = Vec::new();
    let mut current = Vec::new();
    let mut inside = false;
    let mut fence = "";

    for line in content.lines() {
        let trimmed = line.trim();
        if !inside && (trimmed.starts_with("```") || trimmed.starts_with("~~~")) {
            inside = true;
            fence = if trimmed.starts_with("```") {
                "```"
            } else {
                "~~~"
            };
            current.clear();
            continue;
        }

        if inside && trimmed.starts_with(fence) {
            inside = false;
            blocks.push(current.join("\n"));
            current.clear();
            continue;
        }

        if inside {
            current.push(line.to_string());
        }
    }

    blocks
}

fn yaml_requires_swarm_ownership_bootstrap(
    document: &YamlValue,
    image_runtime_users: &BTreeMap<String, String>,
) -> bool {
    let Some(services) = document
        .as_mapping()
        .and_then(|mapping| mapping.get(YamlValue::String("services".to_string())))
        .and_then(YamlValue::as_mapping)
    else {
        return false;
    };

    services
        .values()
        .filter_map(YamlValue::as_mapping)
        .any(|service| {
            service_uses_writable_named_volume(service)
                && service_runs_as_non_root(service, image_runtime_users)
        })
}

fn service_runs_as_non_root(
    service: &serde_yaml::Mapping,
    image_runtime_users: &BTreeMap<String, String>,
) -> bool {
    if let Some(user) = service
        .get(YamlValue::String("user".to_string()))
        .and_then(yaml_scalar_to_string)
    {
        return !is_root_user(&user);
    }

    let Some(image) = service
        .get(YamlValue::String("image".to_string()))
        .and_then(yaml_scalar_to_string)
    else {
        return false;
    };
    let Ok(normalized_image) = normalize_image_reference(image.trim()) else {
        return false;
    };
    let tag_normalized_image = image
        .trim()
        .split_once('@')
        .and_then(|(tagged_image, _)| normalize_image_reference(tagged_image.trim()).ok());
    let image_base = normalized_image
        .split_once('@')
        .map(|(head, _)| head)
        .map_or(normalized_image.as_str(), |value| value);

    resolve_image_runtime_user(
        &normalized_image,
        tag_normalized_image.as_deref(),
        image_base,
        image_runtime_users,
    )
    .is_some_and(|user| !is_root_user(&user))
}

fn profile_runtime_user(document: &YamlValue) -> Option<String> {
    if let Some(user) = yaml_mapping_string(document, &["runtime", "user"]) {
        if runtime_user_value_is_resolved(&user) {
            return Some(user);
        }
    }

    let uid = yaml_mapping_u32(document, &["researched_config", "runtime_uid"]);
    let gid = yaml_mapping_u32(document, &["researched_config", "runtime_gid"]);
    match (uid, gid) {
        (Some(uid), Some(gid)) => Some(format!("{uid}:{gid}")),
        (Some(uid), None) => Some(uid.to_string()),
        (None, Some(_)) | (None, None) => None,
    }
}

fn image_runtime_user_from_yaml(document: &YamlValue) -> Option<(String, String)> {
    let image = yaml_mapping_string(document, &["image"])?;
    let runtime_user = profile_runtime_user(document)?;
    normalize_image_reference(&image)
        .ok()
        .map(|normalized| (normalized, runtime_user))
}

fn resolve_image_runtime_user(
    normalized_image: &str,
    tag_normalized_image: Option<&str>,
    image_base: &str,
    image_runtime_users: &BTreeMap<String, String>,
) -> Option<String> {
    if let Some(user) = image_runtime_users.get(normalized_image) {
        return Some(user.clone());
    }

    if let Some(tag_normalized_image) = tag_normalized_image {
        if let Some(user) = image_runtime_users.get(tag_normalized_image) {
            return Some(user.clone());
        }
    }

    if let Some(user) = image_runtime_users.iter().find_map(|(candidate, user)| {
        let candidate_base = candidate
            .split_once('@')
            .map(|(head, _)| head)
            .map_or(candidate.as_str(), |value| value);
        if candidate_base == image_base {
            Some(user.clone())
        } else {
            None
        }
    }) {
        return Some(user);
    }

    researched_config_for_image(normalized_image, &RuntimeSignatures::default())
        .ok()
        .flatten()
        .and_then(|config| match (config.runtime_uid, config.runtime_gid) {
            (Some(uid), Some(gid)) => Some(format!("{uid}:{gid}")),
            (Some(uid), None) => Some(uid.to_string()),
            (None, Some(_)) | (None, None) => None,
        })
}

fn non_fenced_lines(content: &str) -> Vec<String> {
    let mut lines = Vec::new();
    let mut fence_state = FenceState::Outside;

    for line in content.lines() {
        let trimmed = line.trim();
        if let Some(state) = update_fence_state(fence_state, trimmed) {
            fence_state = state;
            continue;
        }

        if fence_state == FenceState::Outside {
            lines.push(line.to_string());
        }
    }

    lines
}

fn image_runtime_user_from_line(line: &str) -> Option<(String, String)> {
    if let Some(pair) = image_runtime_user_from_table_row(line) {
        return Some(pair);
    }
    let runtime_user = explicit_runtime_user_from_line(line)?;
    let normalized_image = extract_image_references_from_line(line)
        .into_iter()
        .next()?;
    Some((normalized_image, runtime_user))
}

fn extract_image_references_from_line(line: &str) -> Vec<String> {
    let mut images = Vec::new();
    for token in line.split_whitespace() {
        let cleaned = token
            .trim_matches(|c: char| {
                matches!(
                    c,
                    '`' | '*' | '_' | '[' | ']' | '(' | ')' | '{' | '}' | ',' | ';' | '.'
                )
            })
            .trim_matches('|');
        if cleaned.is_empty()
            || !(cleaned.contains('/')
                || cleaned.contains('.')
                || cleaned.contains(':')
                || cleaned.contains('@'))
        {
            continue;
        }
        let Ok(normalized) = normalize_image_reference(cleaned) else {
            continue;
        };
        if !images.contains(&normalized) {
            images.push(normalized);
        }
    }
    images
}

fn image_runtime_user_from_table_row(line: &str) -> Option<(String, String)> {
    if !line.contains('|') {
        return None;
    }

    let cells: Vec<&str> = line
        .split('|')
        .map(str::trim)
        .filter(|cell| !cell.is_empty())
        .collect();
    if cells.len() < 2
        || cells.iter().all(|cell| {
            cell.chars()
                .all(|ch| ch == '-' || ch == ':' || ch.is_whitespace())
        })
    {
        return None;
    }

    let normalized_image = cells.iter().find_map(|cell| {
        let normalized_cell = strip_markdown_cell_wrappers(cell);
        if !normalized_cell.contains('/')
            && !normalized_cell.contains('.')
            && !normalized_cell.contains(':')
            && !normalized_cell.contains('@')
        {
            return None;
        }
        normalize_image_reference(&normalized_cell).ok()
    })?;
    let runtime_user = cells
        .iter()
        .filter_map(|cell| {
            let normalized_cell = strip_markdown_cell_wrappers(cell);
            bare_runtime_user_value(&normalized_cell)
                .or_else(|| explicit_runtime_user_from_line(&normalized_cell))
        })
        .next()?;
    Some((normalized_image, runtime_user))
}

fn strip_markdown_cell_wrappers(cell: &str) -> String {
    cell.trim()
        .trim_matches(|c: char| matches!(c, '`' | '*' | '_'))
        .trim()
        .to_string()
}

const NAMED_RUNTIME_USER_PATTERN: &str = r"[a-z_][a-z0-9_]*(?:-[a-z0-9_]+)*";

fn explicit_runtime_user_from_line(line: &str) -> Option<String> {
    let text = line.trim();
    if text.is_empty() {
        return None;
    }

    let user_pattern = Regex::new(&format!(
        r"(?ix)
        \b(?:runtime\s+user|runs?\s+as|user|uid:gid)\b
        [^A-Za-z0-9]*
        (root|0(?::0)?|[1-9][0-9]*(?::[0-9]+)?|{NAMED_RUNTIME_USER_PATTERN})
        \b",
    ))
    .ok()?;
    if let Some(captures) = user_pattern.captures(text) {
        let runtime_user = captures.get(1).map(|value| value.as_str().to_string())?;
        if ignored_runtime_user_token(&runtime_user) {
            return None;
        }
        return Some(runtime_user);
    }

    let uid_gid_pattern = Regex::new(
        r"(?ix)
        \buid\b[^0-9]*([0-9]+)\b
        .*?
        \bgid\b[^0-9]*([0-9]+)\b
        ",
    )
    .ok()?;
    uid_gid_pattern.captures(text).map(|captures| {
        let uid = captures.get(1).map_or("", |value| value.as_str());
        let gid = captures.get(2).map_or("", |value| value.as_str());
        format!("{uid}:{gid}")
    })
}

fn bare_runtime_user_value(text: &str) -> Option<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return None;
    }

    let user_value_pattern = Regex::new(&format!(
        r"(?i)^(root|0(?::0)?|[1-9][0-9]*(?::[0-9]+)?|{NAMED_RUNTIME_USER_PATTERN})$"
    ))
    .ok()?;
    if let Some(captures) = user_value_pattern.captures(trimmed) {
        let runtime_user = captures.get(1).map(|value| value.as_str().to_string())?;
        if ignored_runtime_user_token(&runtime_user) {
            return None;
        }
        return Some(runtime_user);
    }

    let uid_gid_pattern =
        Regex::new(r"(?ix)^\s*uid\b[^0-9]*([0-9]+)\b.*\bgid\b[^0-9]*([0-9]+)\b\s*$").ok()?;
    uid_gid_pattern.captures(trimmed).map(|captures| {
        let uid = captures.get(1).map_or("", |value| value.as_str());
        let gid = captures.get(2).map_or("", |value| value.as_str());
        format!("{uid}:{gid}")
    })
}

fn yaml_mapping_string(document: &YamlValue, path: &[&str]) -> Option<String> {
    yaml_path_value(document, path)
        .and_then(yaml_scalar_to_string)
        .map(|value| value.trim().to_string())
}

fn yaml_mapping_u32(document: &YamlValue, path: &[&str]) -> Option<u32> {
    let value = yaml_path_value(document, path)?;
    match value {
        YamlValue::Number(number) => number.as_u64().and_then(|value| u32::try_from(value).ok()),
        YamlValue::String(text) => {
            let trimmed = text.trim();
            if trimmed.is_empty() || trimmed.eq_ignore_ascii_case("unknown") {
                return None;
            }
            trimmed.parse::<u32>().ok()
        }
        _ => None,
    }
}

fn yaml_path_value<'a>(document: &'a YamlValue, path: &[&str]) -> Option<&'a YamlValue> {
    let mut current = document;
    for segment in path {
        current = current
            .as_mapping()?
            .get(YamlValue::String((*segment).to_string()))?;
    }
    Some(current)
}

fn yaml_scalar_to_string(value: &YamlValue) -> Option<String> {
    match value {
        YamlValue::String(text) => Some(text.to_string()),
        YamlValue::Number(number) => Some(number.to_string()),
        _ => None,
    }
}

fn runtime_user_value_is_resolved(user: &str) -> bool {
    !user.is_empty() && !user.eq_ignore_ascii_case("unknown")
}

fn ignored_runtime_user_token(user: &str) -> bool {
    user.eq_ignore_ascii_case("unknown")
        || user.eq_ignore_ascii_case("non")
        || user.eq_ignore_ascii_case("non-root")
}

fn is_root_user(user: &str) -> bool {
    let normalized = user.trim().to_ascii_lowercase();
    normalized.is_empty()
        || normalized == "root"
        || normalized == "0"
        || normalized == "0:0"
        || normalized.starts_with("0:")
}

#[cfg(test)]
mod tests {
    use super::validate_output_contract;

    #[test]
    fn validate_output_contract_accepts_well_formed_compose_sections() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Deployment Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "compose").expect("validation should succeed");
        assert!(result.errors.is_empty());
        assert!(result.warnings.is_empty());
    }

    #[test]
    fn validate_output_contract_reports_missing_sections() {
        let doc = "# Requirements\nAC-1\n";
        let result = validate_output_contract(doc, "compose").expect("validation should succeed");
        assert!(!result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_ignores_headings_inside_code_fences() {
        let doc = r#"
# Requirements
AC-CMP-READONLY
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
```dockerfile
# Deployment Overview
RUN echo hi
```
# Unknown Unknowns
RSK-1
# Deployment Overview
AC-2
# Architecture Plan
## Subheading
AC-CMP-NNP
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "compose").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_ignores_headings_inside_tilde_fences() {
        let doc = r#"
# Requirements
AC-CMP-READONLY
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
~~~yaml
# Unknown Unknowns
items:
  - one
~~~
# Unknown Unknowns
RSK-1
# Deployment Overview
AC-2
# Architecture Plan
AC-CMP-NNP
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "compose").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_accepts_hyphenated_markers() {
        let doc = r#"
# Requirements
AC-CMP-READONLY
# Mode Applicability Matrix
O-CMP-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-CMP-1
# Deployment Overview
AC-CMP-2
# Architecture Plan
AC-CMP-3
# Visualization
O-CMP-2
# Task List
AC-CMP-4
# Directory/Prerequisites
O-CMP-3
# Configuration Files
IMG-CMP-2
# Operational Guide
RSK-CMP-2
"#;
        let result = validate_output_contract(doc, "compose").expect("validation should succeed");
        assert!(result.errors.is_empty());
        assert!(result.warnings.is_empty());
    }

    #[test]
    fn validate_output_contract_accepts_well_formed_swarm_sections() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    image: nginx:1.27
    user: "1000:1000"
    volumes:
      - app-data:/data
volumes:
  app-data: {}
```
# Ownership Bootstrap
AC-5
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
        assert!(result.warnings.is_empty());
    }

    #[test]
    fn validate_output_contract_allows_stateless_swarm_without_bootstrap_section() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    image: nginx:1.27
    read_only: true
networks:
  backend:
    driver: overlay
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
        assert!(result.warnings.is_empty());
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_non_root_named_volume_swarm() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    image: nginx:1.27
    user: "1000:1000"
    volumes:
      - app-data:/data
volumes:
  app-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_merged_non_root_named_volume_swarm() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
x-stateful-defaults: &stateful_defaults
  user: "999:999"
  volumes:
    - db-data:/var/lib/postgresql/data
services:
  db:
    <<: *stateful_defaults
    image: postgres:16-alpine
volumes:
  db-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_allows_merged_root_override_for_non_root_image() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
x-stateful-defaults: &stateful_defaults
  user: "999:999"
  volumes:
    - db-data:/var/lib/postgresql/data
x-root-override: &root_override
  user: "0:0"
services:
  db:
    <<: [*root_override, *stateful_defaults]
    image: postgres:16-alpine
volumes:
  db-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_enforces_bootstrap_order_for_non_root_named_volume_swarm() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    image: nginx:1.27
    user: "1000:1000"
    volumes:
      - app-data:/data
volumes:
  app-data: {}
```
# Operational Guide
RSK-2
# Ownership Bootstrap
AC-5
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item == "section out of order: Operational Guide"));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_marker_for_non_root_named_volume_swarm() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    image: nginx:1.27
    user: "1000:1000"
    volumes:
      - app-data:/data
volumes:
  app-data: {}
```
# Ownership Bootstrap
Run a one-shot bootstrap job before deploy.
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item == "missing traceability marker in section: Ownership Bootstrap"));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_image_default_non_root_swarm() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
```yaml
id: IMG-1
image: docker.io/library/postgres:16.4-alpine
runtime:
  user: unknown
researched_config:
  runtime_uid: 999
  runtime_gid: 999
```
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  db:
    image: docker.io/library/postgres:16.4-alpine
    volumes:
      - db-data:/var/lib/postgresql/data
volumes:
  db-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_non_yaml_image_research_line() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1 custom.registry.example/team/app:1.2 runtime user 1001:1002 from upstream docs.
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  app:
    image: custom.registry.example/team/app:1.2
    volumes:
      - app-data:/srv/app/data
volumes:
  app-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_non_yaml_image_research_table() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
| Image | Runtime User | Notes |
| --- | --- | --- |
| ghcr.io/example/worker:2.0 | 1234:1234 | upstream image default |
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  worker:
    image: ghcr.io/example/worker:2.0
    volumes:
      - worker-data:/var/lib/worker
volumes:
  worker-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_markdown_code_image_research_table() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
| Image | Runtime User | Notes |
| --- | --- | --- |
| `ghcr.io/example/worker:2.0` | `1234:1234` | non-root default |
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  worker:
    image: ghcr.io/example/worker:2.0
    volumes:
      - worker-data:/var/lib/worker
volumes:
  worker-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_non_yaml_named_runtime_user_line() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1 ghcr.io/example/worker:2.0 runs as nginx according to upstream docs.
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  worker:
    image: ghcr.io/example/worker:2.0
    volumes:
      - worker-data:/var/lib/worker
volumes:
  worker-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_hyphenated_runtime_user_line() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1 ghcr.io/example/worker:2.0 runs as www-data according to upstream docs.
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  worker:
    image: ghcr.io/example/worker:2.0
    volumes:
      - worker-data:/var/lib/worker
volumes:
  worker-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_non_yaml_named_runtime_user_table() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
| Image | Runtime User | Notes |
| --- | --- | --- |
| ghcr.io/example/worker:2.0 | appuser | upstream image default |
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  worker:
    image: ghcr.io/example/worker:2.0
    volumes:
      - worker-data:/var/lib/worker
volumes:
  worker-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_hyphenated_runtime_user_table() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
| Image | Runtime User | Notes |
| --- | --- | --- |
| ghcr.io/example/worker:2.0 | www-data | upstream image default |
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  worker:
    image: ghcr.io/example/worker:2.0
    volumes:
      - worker-data:/var/lib/worker
volumes:
  worker-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_merged_image_research_yaml_runtime_user() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
```yaml
defaults: &defaults
  runtime:
    user: "1234:1234"
image: ghcr.io/example/worker:2.0
<<: *defaults
```
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  worker:
    image: ghcr.io/example/worker:2.0
    volumes:
      - worker-data:/var/lib/worker
volumes:
  worker-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_from_knowledge_when_research_is_non_structured()
    {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1 reviewed upstream postgres docs and image metadata.
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  db:
    image: postgres:16-alpine
    volumes:
      - db-data:/var/lib/postgresql/data
volumes:
  db-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_ignores_vague_non_yaml_research_without_runtime_user() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1 custom.registry.example/team/app:1.2 may run as non-root, but the docs are inconclusive.
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  app:
    image: custom.registry.example/team/app:1.2
    volumes:
      - app-data:/srv/app/data
volumes:
  app-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_ignores_vague_non_yaml_research_with_non_root_phrase() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1 ghcr.io/example/worker:2.0 may run as non-root, but the docs are inconclusive.
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  worker:
    image: ghcr.io/example/worker:2.0
    volumes:
      - worker-data:/var/lib/worker
volumes:
  worker-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_requires_bootstrap_for_normalized_image_reference_match() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
```yaml
id: IMG-1
image: docker.io/library/postgres:16.4-alpine
runtime:
  user: unknown
researched_config:
  runtime_uid: 999
  runtime_gid: 999
```
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  db:
    image: postgres:16.4-alpine
    volumes:
      - db-data:/var/lib/postgresql/data
volumes:
  db-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_prefers_exact_digest_research_match_over_base_fallback() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
| Image | Runtime User | Notes |
| --- | --- | --- |
| docker.io/library/postgres@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa | 0:0 | older digest |
| docker.io/library/postgres@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb | 999:999 | exact digest |
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  db:
    image: postgres@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
    volumes:
      - db-data:/var/lib/postgresql/data
volumes:
  db-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_preserves_digest_base_fallback_without_exact_match() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
| Image | Runtime User | Notes |
| --- | --- | --- |
| docker.io/library/postgres:16-alpine | 999:999 | upstream image default |
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  db:
    image: postgres:16-alpine@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
    volumes:
      - db-data:/var/lib/postgresql/data
volumes:
  db-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Ownership Bootstrap")));
    }

    #[test]
    fn validate_output_contract_allows_explicit_root_override_for_non_root_image() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
```yaml
id: IMG-1
image: docker.io/library/postgres:16.4-alpine
runtime:
  user: unknown
researched_config:
  runtime_uid: 999
  runtime_gid: 999
```
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  db:
    image: docker.io/library/postgres:16.4-alpine
    user: "0:0"
    volumes:
      - db-data:/var/lib/postgresql/data
volumes:
  db-data: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_allows_read_only_named_volume_swarm_short_syntax() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    user: "1000:1000"
    volumes:
      - certs:/certs:ro,z
volumes:
  certs: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_allows_read_only_named_volume_swarm_short_syntax_with_nocopy() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    user: "1000:1000"
    volumes:
      - certs:/certs:ro,nocopy
volumes:
  certs: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_allows_read_only_named_volume_swarm_when_rw_precedes_ro() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    user: "1000:1000"
    volumes:
      - certs:/certs:rw,ro
volumes:
  certs: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_allows_read_only_named_volume_swarm_long_syntax() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Stack Overview
AC-2
# Architecture Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Directory/Prerequisites
O-3
# Configuration Files
IMG-2
```yaml
services:
  api:
    user: "1000:1000"
    volumes:
      - type: volume
        source: shared-assets
        target: /assets
        read_only: true
volumes:
  shared-assets: {}
```
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "swarm").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_warns_when_image_bake_content_is_missing() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Build Overview
AC-2
# Build Design Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Project Layout/Prerequisites
O-3
# Generated Files
IMG-2
# Operational Guide
RSK-2
"#;
        let result = validate_output_contract(doc, "image").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("docker-bake.hcl")));
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("bake/buildx")));
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("sbom attestation")));
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("provenance attestation")));
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("signing guidance")));
    }

    #[test]
    fn validate_output_contract_accepts_complete_image_release_guidance() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Build Overview
AC-2
# Build Design Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Project Layout/Prerequisites
O-3
# Generated Files
IMG-2 includes docker-bake.hcl
# Operational Guide
RSK-2 run docker buildx bake release --set *.platform=linux/amd64,linux/arm64 --attest type=sbom --attest type=provenance,mode=max and cosign sign example
"#;
        let result = validate_output_contract(doc, "image").expect("validation should succeed");
        assert!(result.errors.is_empty());
    }

    #[test]
    fn validate_output_contract_requires_bake_invocation_guidance_even_with_bake_file_reference() {
        let doc = r#"
# Requirements
AC-1
# Mode Applicability Matrix
O-1
# Image Research
IMG-1
# Unknown Unknowns
RSK-1
# Build Overview
AC-2
# Build Design Plan
AC-3
# Visualization
O-2
# Task List
AC-4
# Project Layout/Prerequisites
O-3
# Generated Files
IMG-2 includes docker-bake.hcl
# Operational Guide
RSK-2 run cosign sign example --attest type=sbom --attest type=provenance,mode=max
"#;
        let result = validate_output_contract(doc, "image").expect("validation should succeed");
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("bake/buildx guidance")));
    }
}
