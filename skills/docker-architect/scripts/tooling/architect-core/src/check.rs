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
/// use architect_core::check::validate_cache;
/// use architect_core::model::CachedProfiles;
///
/// let warnings = validate_cache(
///     &CachedProfiles {
///         schema_version: 2,
///         profiles: Vec::new(),
///         unresolved_references: Vec::new(),
///     },
///     "advisory",
/// )
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
    let mut critical = Vec::new();
    for (index, reference) in cache.unresolved_references.iter().enumerate() {
        let issue = format!("RSK-{} unresolved image reference: {reference}", index + 1);
        warnings.push(issue.clone());
        if strictness == "enforcing" {
            critical.push(issue);
        }
    }

    for profile in &cache.profiles {
        if profile.digest.is_none() {
            let issue = format!("{} missing digest", profile.id);
            warnings.push(issue.clone());
            critical.push(issue);
        }
        if profile.docs_url.is_none() {
            let issue = format!("{} missing docs url", profile.id);
            if is_docker_hub_image(&profile.image) {
                critical.push(issue.clone());
            }
            warnings.push(issue);
        }
        if profile.dockerfile_url.is_none() {
            let issue = format!("{} missing dockerfile url", profile.id);
            if is_docker_hub_image(&profile.image) {
                critical.push(issue.clone());
            }
            warnings.push(issue);
        }
        if profile.platforms.is_empty() {
            warnings.push(format!("{} missing platforms", profile.id));
        }
        if is_docker_hub_image(&profile.image) && runtime_user_is_unresolved(&profile.runtime.user)
        {
            let issue = match (
                profile.researched_config.runtime_uid,
                profile.researched_config.runtime_gid,
            ) {
                (Some(uid), Some(gid)) => format!(
                    "{} missing deterministic runtime user; curated knowledge suggests {}:{}",
                    profile.id, uid, gid
                ),
                (Some(uid), None) => format!(
                    "{} missing deterministic runtime user; curated knowledge suggests uid {}",
                    profile.id, uid
                ),
                _ => format!("{} missing deterministic runtime user", profile.id),
            };
            warnings.push(issue.clone());
            critical.push(issue);
        }
    }

    if strictness == "enforcing" && (!warnings.is_empty() || !critical.is_empty()) {
        return Err(AppError::InvalidInput {
            reason: format!("enforcing validation failed: {}", warnings.join("; ")),
        });
    }

    if strictness == "balanced" && !critical.is_empty() {
        return Err(AppError::InvalidInput {
            reason: format!("balanced validation failed: {}", critical.join("; ")),
        });
    }

    Ok(warnings)
}

fn is_docker_hub_image(image: &str) -> bool {
    image.starts_with("docker.io/")
}

fn runtime_user_is_unresolved(user: &Option<String>) -> bool {
    user.as_deref()
        .map(str::trim)
        .is_none_or(|value| value.is_empty() || value.eq_ignore_ascii_case("unknown"))
}

#[cfg(test)]
mod tests {
    use super::validate_cache;
    use crate::model::{CachedProfiles, ImageProfile, Platform, RuntimeProfile};

    fn base_profile(image: &str) -> ImageProfile {
        ImageProfile {
            id: "IMG-1".to_string(),
            image: image.to_string(),
            docs_url: Some("https://example.com/docs".to_string()),
            dockerfile_url: Some("https://example.com/repo".to_string()),
            digest: Some("sha256:abc".to_string()),
            config_digest: Some("sha256:def".to_string()),
            platforms: vec![Platform {
                os: "linux".to_string(),
                arch: "amd64".to_string(),
            }],
            runtime: RuntimeProfile::default(),
            sources: Vec::new(),
            notes: Vec::new(),
            researched_config: Default::default(),
        }
    }

    #[test]
    fn balanced_rejects_missing_docs_for_docker_hub_image() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.docs_url = None;
        let cache = CachedProfiles {
            schema_version: 1,
            profiles: vec![profile],
            unresolved_references: Vec::new(),
        };

        let result = validate_cache(&cache, "balanced");
        assert!(matches!(
            result,
            Err(crate::error::AppError::InvalidInput { .. })
        ));
    }

    #[test]
    fn balanced_rejects_missing_dockerfile_for_docker_hub_image() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.dockerfile_url = None;
        let cache = CachedProfiles {
            schema_version: 1,
            profiles: vec![profile],
            unresolved_references: Vec::new(),
        };

        let result = validate_cache(&cache, "balanced");
        assert!(matches!(
            result,
            Err(crate::error::AppError::InvalidInput { .. })
        ));
    }

    #[test]
    fn balanced_allows_missing_docs_for_non_docker_hub_image() {
        let mut profile = base_profile("ghcr.io/openfaas/gateway:latest");
        profile.docs_url = None;
        let cache = CachedProfiles {
            schema_version: 1,
            profiles: vec![profile],
            unresolved_references: Vec::new(),
        };

        let result = validate_cache(&cache, "balanced");
        assert!(result.is_ok());
    }

    #[test]
    fn balanced_rejects_missing_digest_for_non_docker_hub_image() {
        let mut profile = base_profile("ghcr.io/openfaas/gateway:latest");
        profile.digest = None;
        let cache = CachedProfiles {
            schema_version: 1,
            profiles: vec![profile],
            unresolved_references: Vec::new(),
        };

        let result = validate_cache(&cache, "balanced");
        assert!(matches!(
            result,
            Err(crate::error::AppError::InvalidInput { .. })
        ));
    }

    #[test]
    fn balanced_rejects_missing_runtime_user_for_docker_hub_image() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.runtime.user = None;
        profile.researched_config.runtime_uid = Some(1000);
        profile.researched_config.runtime_gid = Some(1000);
        let cache = CachedProfiles {
            schema_version: 1,
            profiles: vec![profile],
            unresolved_references: Vec::new(),
        };

        let result = validate_cache(&cache, "balanced");
        assert!(matches!(
            result,
            Err(crate::error::AppError::InvalidInput { .. })
        ));
    }

    #[test]
    fn enforcing_rejects_unresolved_references() {
        let profile = base_profile("docker.io/library/nginx:1.27");
        let cache = CachedProfiles {
            schema_version: 2,
            profiles: vec![profile],
            unresolved_references: vec!["nginx:${TAG}".to_string()],
        };

        let result = validate_cache(&cache, "enforcing");
        assert!(matches!(
            result,
            Err(crate::error::AppError::InvalidInput { .. })
        ));
    }
}
