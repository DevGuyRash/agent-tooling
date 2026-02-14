//! Image reference extraction utilities.

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
                let normalized_reference = reference.to_lowercase();
                let is_stage_alias = !normalized_reference.contains('/')
                    && !normalized_reference.contains(':')
                    && !normalized_reference.contains('@')
                    && stage_aliases.contains(&normalized_reference);
                if !reference.is_empty() && !is_stage_alias {
                    candidates.push(reference.to_string());
                }

                if tokens.len() >= 3 && tokens[1].eq_ignore_ascii_case("as") {
                    stage_aliases.insert(tokens[2].to_lowercase());
                }
            }
        }
    }

    classify_images(&candidates)
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
}
