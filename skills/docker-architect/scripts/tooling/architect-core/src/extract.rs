//! Image reference extraction utilities.

use std::collections::BTreeMap;
use std::collections::BTreeSet;

use regex::Regex;
use serde::Serialize;

use crate::error::AppError;

/// Deterministic extraction output separated by resolvability.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ExtractedImages {
    /// Fully-resolved image references that can be refreshed against registries.
    pub valid: Vec<String>,
    /// References that include interpolation or unresolved symbols.
    pub unresolved: Vec<String>,
}

/// Extract unique image references from text.
///
/// # Arguments
/// * `input` - Text containing compose YAML, Dockerfile content, or snippets.
///
/// # Returns
/// * `Ok(Vec<String>)` containing stable-sorted, valid image references.
/// * `Err(AppError)` when extraction cannot proceed.
///
/// # Examples
/// ```
/// use architect_core::extract::extract_images;
///
/// let text = "image: nginx:1.27\nFROM redis:7";
/// let images = extract_images(text).expect("extract should succeed");
/// assert_eq!(images, vec!["nginx:1.27", "redis:7"]);
/// ```
pub fn extract_images(input: &str) -> Result<Vec<String>, AppError> {
    Ok(extract_image_sets(input)?.valid)
}

/// Extract image references and classify unresolved tokens.
///
/// # Arguments
/// * `input` - Text containing compose YAML, Dockerfile content, or snippets.
///
/// # Returns
/// * `Ok(ExtractedImages)` with deterministic ordering in both sets.
///
/// # Examples
/// ```
/// use architect_core::extract::extract_image_sets;
///
/// let text = "image: nginx:${TAG}\nFROM redis:7";
/// let sets = extract_image_sets(text).expect("extract should succeed");
/// assert_eq!(sets.valid, vec!["redis:7"]);
/// assert_eq!(sets.unresolved, vec!["nginx:${TAG}"]);
/// ```
pub fn extract_image_sets(input: &str) -> Result<ExtractedImages, AppError> {
    let mut candidates = Vec::new();
    let mut stage_aliases = BTreeSet::new();
    let mut arg_defaults: BTreeMap<String, String> = BTreeMap::new();

    let image_re = Regex::new(r#"(?m)^\s*image\s*:\s*["']?([^\s"'#]+)["']?\s*(?:#.*)?$"#).map_err(
        |error| AppError::InvalidInput {
            reason: format!("failed to compile image regex: {error}"),
        },
    )?;

    for capture in image_re.captures_iter(input) {
        if let Some(value) = capture.get(1) {
            candidates.push(value.as_str().to_string());
        }
    }

    for raw_line in input.lines() {
        let line = raw_line.trim();
        if line.starts_with("ARG ") || line.starts_with("arg ") {
            if let Some((name, default)) = parse_arg_default(line) {
                arg_defaults.insert(name, default);
            }
            continue;
        }
        if line.starts_with("FROM ") || line.starts_with("from ") {
            let mut parts = line.split_whitespace();
            let _ = parts.next();
            let mut tokens: Vec<&str> = parts.collect();

            while let Some(first) = tokens.first().copied() {
                if !first.starts_with("--") {
                    break;
                }

                let _ = tokens.remove(0);
                if !first.contains('=')
                    && tokens
                        .first()
                        .copied()
                        .is_some_and(|next| !next.starts_with("--"))
                {
                    let _ = tokens.remove(0);
                }
            }

            if let Some(reference) = tokens.first().copied() {
                let resolved_reference = resolve_from_reference(reference, &arg_defaults);
                let normalized_reference = resolved_reference.to_lowercase();
                let is_stage_alias = !normalized_reference.contains('/')
                    && !normalized_reference.contains(':')
                    && !normalized_reference.contains('@')
                    && stage_aliases.contains(&normalized_reference);
                if !resolved_reference.is_empty() && !is_stage_alias {
                    candidates.push(resolved_reference);
                }

                if tokens.len() >= 3 && tokens[1].eq_ignore_ascii_case("as") {
                    stage_aliases.insert(tokens[2].to_lowercase());
                }
            }
        }
    }

    classify_images(&candidates)
}

fn parse_arg_default(line: &str) -> Option<(String, String)> {
    let mut parts = line.splitn(2, char::is_whitespace);
    let keyword = parts.next()?;
    if !keyword.eq_ignore_ascii_case("ARG") {
        return None;
    }
    let remainder = parts.next()?.trim();
    let (name, value) = remainder.split_once('=')?;
    let key = name.trim();
    if key.is_empty() {
        return None;
    }
    let default = value
        .trim()
        .trim_matches('"')
        .trim_matches('\'')
        .to_string();
    Some((key.to_string(), default))
}

fn resolve_from_reference(reference: &str, arg_defaults: &BTreeMap<String, String>) -> String {
    let bytes = reference.as_bytes();
    let mut output = String::with_capacity(reference.len());
    let mut index = 0usize;

    while index < bytes.len() {
        if bytes[index] != b'$' {
            output.push(bytes[index] as char);
            index += 1;
            continue;
        }

        if index + 1 >= bytes.len() {
            output.push('$');
            index += 1;
            continue;
        }

        if bytes[index + 1] == b'{' {
            let mut end = index + 2;
            while end < bytes.len() && bytes[end] != b'}' {
                end += 1;
            }
            if end < bytes.len() {
                let token = &reference[index + 2..end];
                if is_valid_arg_name(token) {
                    if let Some(value) = arg_defaults.get(token) {
                        output.push_str(value);
                    } else {
                        output.push_str(&reference[index..=end]);
                    }
                    index = end + 1;
                    continue;
                }
            }
            output.push('$');
            index += 1;
            continue;
        }

        let start = index + 1;
        if !is_valid_arg_start(bytes[start]) {
            output.push('$');
            index += 1;
            continue;
        }

        let mut end = start;
        while end < bytes.len() && is_valid_arg_continue(bytes[end]) {
            end += 1;
        }

        let token = &reference[start..end];
        if let Some(value) = arg_defaults.get(token) {
            output.push_str(value);
        } else {
            output.push_str(&reference[index..end]);
        }
        index = end;
    }

    output
}

fn is_valid_arg_name(value: &str) -> bool {
    let mut chars = value.bytes();
    let Some(first) = chars.next() else {
        return false;
    };
    if !is_valid_arg_start(first) {
        return false;
    }
    chars.all(is_valid_arg_continue)
}

fn is_valid_arg_start(byte: u8) -> bool {
    byte.is_ascii_alphabetic() || byte == b'_'
}

fn is_valid_arg_continue(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

/// Normalize and deduplicate image references.
///
/// # Arguments
/// * `images` - Potentially duplicated image references.
///
/// # Returns
/// * Sorted `BTreeSet<String>` of normalized references.
///
/// # Examples
/// ```
/// use architect_core::extract::normalize_images;
///
/// let set = normalize_images(&[" nginx:1.27 ".to_string(), "nginx:1.27".to_string()])
///     .expect("normalize should succeed");
/// assert_eq!(set.len(), 1);
/// ```
pub fn normalize_images(images: &[String]) -> Result<BTreeSet<String>, AppError> {
    let extracted = classify_images(images)?;
    Ok(extracted.valid.into_iter().collect())
}

/// Classify a direct list of image references into valid and unresolved sets.
///
/// # Arguments
/// * `images` - Raw image references supplied by CLI or external inputs.
///
/// # Returns
/// * `Ok(ExtractedImages)` with deterministic ordering.
pub fn classify_image_list(images: &[String]) -> Result<ExtractedImages, AppError> {
    classify_images(images)
}

fn classify_images(images: &[String]) -> Result<ExtractedImages, AppError> {
    let mut valid = BTreeSet::new();
    let mut unresolved = BTreeSet::new();

    for candidate in images {
        let cleaned = clean_image_candidate(candidate);
        if cleaned.is_empty() {
            continue;
        }

        if cleaned.chars().any(char::is_whitespace) {
            return Err(AppError::InvalidInput {
                reason: format!("image reference contains whitespace: {cleaned}"),
            });
        }

        if has_interpolation_syntax(&cleaned) {
            unresolved.insert(cleaned);
            continue;
        }

        let valid_chars = cleaned.chars().all(|ch| {
            ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-' | '/' | ':' | '@')
        });

        if !valid_chars {
            return Err(AppError::InvalidInput {
                reason: format!("image reference contains unsupported characters: {cleaned}"),
            });
        }

        valid.insert(cleaned);
    }

    Ok(ExtractedImages {
        valid: valid.into_iter().collect(),
        unresolved: unresolved.into_iter().collect(),
    })
}

fn clean_image_candidate(candidate: &str) -> String {
    candidate
        .trim()
        .trim_matches('"')
        .trim_matches('`')
        .trim_matches('\'')
        .trim_end_matches(',')
        .to_string()
}

fn has_interpolation_syntax(value: &str) -> bool {
    value.contains('$') || value.contains('{') || value.contains('}')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_images_finds_image_keys_and_from_lines() {
        let input = r#"
services:
  web:
    image: nginx:1.27
  cache:
    image: redis:7
FROM alpine:3.20
"#;

        let actual = extract_images(input).expect("extract should succeed");
        assert_eq!(actual, vec!["alpine:3.20", "nginx:1.27", "redis:7"]);
    }

    #[test]
    fn extract_images_ignores_from_stage_aliases() {
        let input = r#"
FROM rust:1.84 AS builder
RUN cargo build --release
FROM builder AS runtime
COPY --from=builder /app /app
"#;

        let actual = extract_images(input).expect("extract should succeed");
        assert_eq!(actual, vec!["rust:1.84"]);
    }

    #[test]
    fn extract_images_resolves_arg_default_in_from_reference() {
        let input = r#"
ARG RUNTIME_IMAGE=ghcr.io/example/app:1.2.3
FROM ${RUNTIME_IMAGE}
"#;

        let actual = extract_images(input).expect("extract should succeed");
        assert_eq!(actual, vec!["ghcr.io/example/app:1.2.3"]);
    }

    #[test]
    fn normalize_images_rejects_invalid_reference() {
        let result = normalize_images(&["invalid ref".to_string()]);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn normalize_images_preserves_case_for_tags_and_paths() {
        let set = normalize_images(&["ghcr.io/OpenFaaS/Gateway:RC1".to_string()])
            .expect("normalize should succeed");
        assert!(set.contains("ghcr.io/OpenFaaS/Gateway:RC1"));
    }

    #[test]
    fn extract_images_supports_compose_inline_comment() {
        let input = r#"
services:
  web:
    image: nginx:1.27 # pinned
"#;

        let actual = extract_images(input).expect("extract should succeed");
        assert_eq!(actual, vec!["nginx:1.27"]);
    }

    #[test]
    fn extract_image_sets_marks_interpolated_references_unresolved() {
        let input = r#"
services:
  web:
    image: nginx:${NGINX_VERSION}
FROM $BASE_IMAGE
"#;
        let sets = extract_image_sets(input).expect("extract should succeed");
        assert!(sets.valid.is_empty());
        assert_eq!(
            sets.unresolved,
            vec![
                "$BASE_IMAGE".to_string(),
                "nginx:${NGINX_VERSION}".to_string()
            ]
        );
    }

    #[test]
    fn extract_images_resolves_arg_tokens_without_prefix_collisions() {
        let input = r#"
ARG A=docker.io/library/alpine
ARG AB=docker.io/library/debian:12
FROM $AB
"#;
        let actual = extract_images(input).expect("extract should succeed");
        assert_eq!(actual, vec!["docker.io/library/debian:12"]);
    }

    #[test]
    fn extract_images_keeps_unresolved_arg_tokens_when_no_default_is_set() {
        let input = r#"
FROM ${RUNTIME_BASE}
"#;
        let sets = extract_image_sets(input).expect("extract should succeed");
        assert!(sets.valid.is_empty());
        assert_eq!(sets.unresolved, vec!["${RUNTIME_BASE}".to_string()]);
    }
}
