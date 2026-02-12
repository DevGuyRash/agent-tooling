//! Image reference extraction utilities.

use std::collections::BTreeSet;

use regex::Regex;

use crate::error::AppError;

/// Extract unique image references from text.
///
/// # Arguments
/// * `input` - Text containing compose YAML, Dockerfile content, or snippets.
///
/// # Returns
/// * `Ok(Vec<String>)` containing stable-sorted image references.
/// * `Err(AppError)` when extraction cannot proceed.
///
/// # Examples
/// ```
/// use piascs::extract::extract_images;
///
/// let text = "image: nginx:1.27\nFROM redis:7";
/// let images = extract_images(text).expect("extract should succeed");
/// assert_eq!(images, vec!["nginx:1.27", "redis:7"]);
/// ```
pub fn extract_images(input: &str) -> Result<Vec<String>, AppError> {
    let mut candidates = Vec::new();

    let image_re =
        Regex::new(r#"(?m)^\s*image\s*:\s*["']?([^\s"'#]+)["']?\s*$"#).map_err(|error| {
            AppError::InvalidInput {
                reason: format!("failed to compile image regex: {error}"),
            }
        })?;

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
            if let Some(first_token) = parts.next() {
                let reference = if first_token.starts_with("--") {
                    parts.next().unwrap_or_default()
                } else {
                    first_token
                };
                if !reference.is_empty() {
                    candidates.push(reference.to_string());
                }
            }
        }
    }

    let normalized = normalize_images(&candidates)?;
    Ok(normalized.into_iter().collect())
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
/// use piascs::extract::normalize_images;
///
/// let set = normalize_images(&[" Nginx:1.27 ".to_string(), "nginx:1.27".to_string()])
///     .expect("normalize should succeed");
/// assert_eq!(set.len(), 1);
/// ```
pub fn normalize_images(images: &[String]) -> Result<BTreeSet<String>, AppError> {
    let mut output = BTreeSet::new();

    for candidate in images {
        let cleaned = candidate
            .trim()
            .trim_matches('"')
            .trim_matches('`')
            .trim_matches('\'')
            .trim_end_matches(',')
            .to_lowercase();

        if cleaned.is_empty() {
            continue;
        }

        if cleaned.chars().any(char::is_whitespace) {
            return Err(AppError::InvalidInput {
                reason: format!("image reference contains whitespace: {cleaned}"),
            });
        }

        let valid = cleaned.chars().all(|ch| {
            ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-' | '/' | ':' | '@')
        });

        if !valid {
            return Err(AppError::InvalidInput {
                reason: format!("image reference contains unsupported characters: {cleaned}"),
            });
        }

        output.insert(cleaned);
    }

    Ok(output)
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
    fn normalize_images_rejects_invalid_reference() {
        let result = normalize_images(&["invalid ref".to_string()]);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }
}
