//! Validation routines for strictness gates.

use crate::error::AppError;
use crate::model::{resolved_runtime_user_for_profile, CachedProfiles};

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
            warnings.push(issue);
        }
        if profile.source_repo_url.is_none() && profile.runtime.oci.source.is_none() {
            warnings.push(format!("{} missing source repository url", profile.id));
        }
        if profile.platforms.is_empty() {
            warnings.push(format!("{} missing platforms", profile.id));
        }
        if runtime_identity_is_unresolved(profile) {
            let issue = match (
                profile.researched_config.runtime_uid,
                profile.researched_config.runtime_gid,
            ) {
                (Some(uid), Some(gid)) => format!(
                    "{} missing deterministic runtime user in image config; curated knowledge suggests {}:{}",
                    profile.id, uid, gid
                ),
                (Some(uid), None) => format!(
                    "{} missing deterministic runtime user in image config; curated knowledge suggests uid {}",
                    profile.id, uid
                ),
                _ => format!("{} missing resolved runtime identity", profile.id),
            };
            warnings.push(issue.clone());
            critical.push(issue);
        }
        if healthcheck_is_unresolved(profile) {
            let issue = format!(
                "{} missing resolved healthcheck metadata; neither image config nor curated knowledge provides one",
                profile.id
            );
            warnings.push(issue.clone());
            critical.push(issue);
        }
        if provenance_is_ambiguous(profile) {
            let issue = format!(
                "{} missing resolved provenance; source repository is unknown and no deterministic registry-v2 config provenance was found",
                profile.id
            );
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

fn runtime_identity_is_unresolved(profile: &crate::model::ImageProfile) -> bool {
    runtime_identity_resolution_is_required(profile)
        && runtime_user_is_unresolved(&profile.runtime.user)
        && resolved_runtime_user_for_profile(profile).is_none()
}

fn runtime_identity_resolution_is_required(profile: &crate::model::ImageProfile) -> bool {
    !profile.runtime.exposed_ports.is_empty()
}

fn healthcheck_is_unresolved(profile: &crate::model::ImageProfile) -> bool {
    healthcheck_resolution_is_required(profile)
        && profile.runtime.healthcheck.is_none()
        && profile.researched_config.preferred_healthcheck.is_none()
}

fn healthcheck_resolution_is_required(profile: &crate::model::ImageProfile) -> bool {
    !profile.runtime.exposed_ports.is_empty()
}

fn provenance_is_ambiguous(profile: &crate::model::ImageProfile) -> bool {
    profile.source_repo_url.is_none()
        && profile.runtime.oci.source.is_none()
        && !profile
            .sources
            .iter()
            .any(|source| source.kind == "registry-v2-config" && source.status == "ok")
}

#[cfg(test)]
mod tests {
    use super::validate_cache;
    use crate::model::{
        CachedProfiles, HealthcheckProfile, ImageProfile, Platform, RuntimeProfile,
    };

    fn base_profile(image: &str) -> ImageProfile {
        ImageProfile {
            id: "IMG-1".to_string(),
            image: image.to_string(),
            docs_url: Some("https://example.com/docs".to_string()),
            dockerfile_url: Some("https://example.com/repo/Dockerfile".to_string()),
            source_repo_url: Some("https://example.com/repo".to_string()),
            digest: Some("sha256:abc".to_string()),
            config_digest: Some("sha256:def".to_string()),
            platforms: vec![Platform {
                os: "linux".to_string(),
                arch: "amd64".to_string(),
            }],
            runtime: RuntimeProfile {
                user: Some("1000:1000".to_string()),
                healthcheck: Some(HealthcheckProfile {
                    test: vec!["CMD".to_string(), "true".to_string()],
                    ..HealthcheckProfile::default()
                }),
                ..RuntimeProfile::default()
            },
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
    fn balanced_warns_but_allows_missing_dockerfile_when_provenance_is_resolved() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.dockerfile_url = None;
        let cache = CachedProfiles {
            schema_version: 1,
            profiles: vec![profile],
            unresolved_references: Vec::new(),
        };

        let result = validate_cache(&cache, "balanced");
        let warnings = result.expect("balanced validation should succeed");
        assert!(warnings
            .iter()
            .any(|item| item.contains("missing dockerfile url")));
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
        assert!(result.is_ok());
    }

    #[test]
    fn balanced_rejects_when_runtime_identity_is_fully_unresolved() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.runtime.user = None;
        profile.runtime.exposed_ports = vec!["80/tcp".to_string()];
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
    fn balanced_rejects_ambiguous_provenance() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.source_repo_url = None;
        profile.runtime.oci.source = None;
        profile.sources.clear();
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
    fn balanced_rejects_missing_healthcheck_metadata() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.runtime.healthcheck = None;
        profile.researched_config.preferred_healthcheck = None;
        profile.runtime.exposed_ports = vec!["80/tcp".to_string()];
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
    fn balanced_allows_helper_image_without_runtime_identity() {
        let mut profile = base_profile("docker.io/library/alpine:3.20");
        profile.runtime.user = None;
        profile.runtime.exposed_ports.clear();
        profile.researched_config.runtime_uid = None;
        profile.researched_config.runtime_gid = None;
        let cache = CachedProfiles {
            schema_version: 1,
            profiles: vec![profile],
            unresolved_references: Vec::new(),
        };

        let result = validate_cache(&cache, "balanced");
        assert!(result.is_ok());
    }

    #[test]
    fn balanced_rejects_gid_only_runtime_identity_hint() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.runtime.user = None;
        profile.runtime.exposed_ports = vec!["80/tcp".to_string()];
        profile.researched_config.runtime_uid = None;
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
    fn balanced_allows_uid_only_runtime_identity_hint() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.runtime.user = None;
        profile.runtime.exposed_ports = vec!["80/tcp".to_string()];
        profile.researched_config.runtime_uid = Some(1000);
        profile.researched_config.runtime_gid = None;
        let cache = CachedProfiles {
            schema_version: 1,
            profiles: vec![profile],
            unresolved_references: Vec::new(),
        };

        let result = validate_cache(&cache, "balanced");
        assert!(result.is_ok());
    }

    #[test]
    fn balanced_treats_unknown_runtime_user_as_unresolved() {
        let mut profile = base_profile("docker.io/library/nginx:1.27");
        profile.runtime.user = Some("unknown".to_string());
        profile.runtime.exposed_ports = vec!["80/tcp".to_string()];
        profile.researched_config.runtime_uid = None;
        profile.researched_config.runtime_gid = None;
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
