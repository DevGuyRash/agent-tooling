//! Validation routines for strictness gates.

use crate::error::AppError;
use crate::model::CachedProfiles;

/// Validate cached profiles for a strictness level.
///
/// # Arguments
/// * `cache` - Profile payload to validate.
/// * `strictness` - advisory, balanced, or enforcing.
///
/// # Returns
/// * `Ok(Vec<String>)` warnings list for advisory/balanced mode.
/// * `Err(AppError)` when strict mode fails validation.
///
/// # Examples
/// ```
/// use piascs::check::validate_cache;
/// use piascs::model::CachedProfiles;
///
/// let warnings = validate_cache(&CachedProfiles { schema_version: 1, profiles: Vec::new() }, "advisory")
///     .expect("validation should succeed");
/// assert!(warnings.is_empty());
/// ```
pub fn validate_cache(cache: &CachedProfiles, strictness: &str) -> Result<Vec<String>, AppError> {
    if !matches!(strictness, "advisory" | "balanced" | "enforcing") {
        return Err(AppError::InvalidInput {
            reason: format!("unknown strictness value: {strictness}"),
        });
    }

    let mut warnings = Vec::new();
    for profile in &cache.profiles {
        if profile.digest.is_none() {
            warnings.push(format!("{} missing digest", profile.id));
        }
        if profile.docs_url.is_none() {
            warnings.push(format!("{} missing docs url", profile.id));
        }
        if profile.dockerfile_url.is_none() {
            warnings.push(format!("{} missing dockerfile url", profile.id));
        }
        if profile.platforms.is_empty() {
            warnings.push(format!("{} missing platforms", profile.id));
        }
    }

    if strictness == "enforcing" && !warnings.is_empty() {
        return Err(AppError::InvalidInput {
            reason: format!("enforcing validation failed: {}", warnings.join("; ")),
        });
    }

    if strictness == "balanced" {
        let critical: Vec<&String> = warnings
            .iter()
            .filter(|value| value.contains("missing digest") || value.contains("missing docs url"))
            .collect();
        if !critical.is_empty() {
            return Err(AppError::InvalidInput {
                reason: format!(
                    "balanced validation failed: {}",
                    critical.into_iter().cloned().collect::<Vec<_>>().join("; ")
                ),
            });
        }
    }

    Ok(warnings)
}
