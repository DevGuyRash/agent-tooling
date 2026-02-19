//! Markdown output contract validator for deterministic skill responses.

use regex::Regex;

use crate::error::AppError;

/// Validate markdown content against required section order and traceability IDs.
///
/// # Arguments
/// * `content` - Markdown payload to validate.
/// * `mode` - Workflow mode, `compose` or `image`.
///
/// # Returns
/// * `Ok(Vec<String>)` with validation errors; empty means pass.
/// * `Err(AppError)` when mode is unsupported.
pub fn validate_output_contract(content: &str, mode: &str) -> Result<Vec<String>, AppError> {
    let required_sections = match mode {
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

    let headings = collect_headings(content);
    let mut errors = Vec::new();

    let mut previous_index = None;
    for section in &required_sections {
        let current_index = headings
            .iter()
            .position(|(_, heading)| heading.eq_ignore_ascii_case(section));
        match current_index {
            Some(position) => {
                if previous_index.is_some_and(|prior| position < prior) {
                    errors.push(format!("section out of order: {section}"));
                }
                previous_index = Some(position);
            }
            None => {
                errors.push(format!("missing required section: {section}"));
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
                errors.push(format!("missing traceability marker in section: {section}"));
            }
        }
    }

    for marker in ["AC-", "IMG-", "RSK-", "O-"] {
        if !content.contains(marker) {
            errors.push(format!("missing marker family: {marker}*"));
        }
    }

    Ok(errors)
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
        assert!(result.is_empty());
    }

    #[test]
    fn validate_output_contract_reports_missing_sections() {
        let doc = "# Requirements\nAC-1\n";
        let result = validate_output_contract(doc, "compose").expect("validation should succeed");
        assert!(!result.is_empty());
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
        assert!(result.is_empty());
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
        assert!(result.is_empty());
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
        assert!(result.is_empty());
    }
}
