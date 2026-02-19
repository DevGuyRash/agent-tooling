//! Versioned curated image knowledge used by deterministic compose/image synthesis.

use std::sync::OnceLock;

use serde::Deserialize;

use crate::error::AppError;
use crate::model::{
    ComposeHealthcheckTemplate, RecommendedEnvVar, ResearchedConfig, RuntimeSignatures,
};

const KNOWLEDGE_V1: &str = include_str!("../../../../references/image-knowledge/knowledge.v1.yaml");

/// Compiled curated knowledge base.
#[derive(Debug, Clone, Deserialize)]
pub struct KnowledgeBase {
    /// Schema version.
    pub version: u32,
    /// Curated image entries.
    #[serde(default)]
    pub images: Vec<KnowledgeImage>,
}

/// One curated image entry.
#[derive(Debug, Clone, Deserialize)]
pub struct KnowledgeImage {
    /// Stable knowledge entry identifier.
    pub id: String,
    /// Match selector for image references.
    #[serde(rename = "match")]
    pub matcher: KnowledgeImageMatch,
    /// Known runtime UID.
    #[serde(default)]
    pub runtime_uid: Option<u32>,
    /// Known runtime GID.
    #[serde(default)]
    pub runtime_gid: Option<u32>,
    /// Writable mounts expected for the image family.
    #[serde(default)]
    pub required_mounts: Vec<String>,
    /// Curated environment recommendations.
    #[serde(default)]
    pub recommended_env: Vec<RecommendedEnvVar>,
    /// Preferred healthcheck template.
    #[serde(default)]
    pub preferred_healthcheck: Option<ComposeHealthcheckTemplate>,
    /// Preferred GPU driver.
    #[serde(default)]
    pub preferred_gpu_driver: Option<String>,
    /// Preferred GPU capabilities.
    #[serde(default)]
    pub preferred_gpu_capabilities: Vec<String>,
    /// Security notes attached to this entry.
    #[serde(default)]
    pub security_notes: Vec<String>,
}

/// Image matching selector for one curated entry.
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(default)]
pub struct KnowledgeImageMatch {
    /// Allowed registries.
    pub registries: Vec<String>,
    /// Allowed repositories.
    pub repositories: Vec<String>,
    /// Prefix matches against normalized image references.
    pub image_prefixes: Vec<String>,
}

/// Load the embedded knowledge base.
pub fn knowledge_base() -> Result<&'static KnowledgeBase, AppError> {
    static CACHE: OnceLock<KnowledgeBase> = OnceLock::new();
    if let Some(cached) = CACHE.get() {
        return Ok(cached);
    }

    let parsed: KnowledgeBase =
        serde_yaml::from_str(KNOWLEDGE_V1).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse embedded image knowledge: {error}"),
        })?;
    if parsed.version != 1 {
        return Err(AppError::InvalidInput {
            reason: format!(
                "unsupported image knowledge schema version: {}",
                parsed.version
            ),
        });
    }

    let _ = CACHE.set(parsed);
    CACHE.get().ok_or_else(|| AppError::InvalidInput {
        reason: "failed to initialize embedded image knowledge cache".to_string(),
    })
}

/// Resolve curated researched configuration for a normalized image reference.
pub fn researched_config_for_image(
    normalized_image: &str,
    signatures: &RuntimeSignatures,
) -> Result<Option<ResearchedConfig>, AppError> {
    let Some(parts) = ImageParts::parse(normalized_image) else {
        return Ok(None);
    };
    let base = knowledge_base()?;
    let Some(entry) = base
        .images
        .iter()
        .find(|candidate| candidate.matcher.matches(&parts))
    else {
        return Ok(None);
    };

    let mut config = ResearchedConfig {
        recommended_env: entry.recommended_env.clone(),
        required_mounts: entry.required_mounts.clone(),
        security_notes: entry.security_notes.clone(),
        runtime_uid: entry.runtime_uid,
        runtime_gid: entry.runtime_gid,
        preferred_healthcheck: entry.preferred_healthcheck.clone(),
        preferred_gpu_driver: entry.preferred_gpu_driver.clone(),
        preferred_gpu_capabilities: entry.preferred_gpu_capabilities.clone(),
    };
    config
        .security_notes
        .push(format!("knowledge-id:{}", entry.id));

    if signatures.gpu_compute && config.preferred_gpu_capabilities.is_empty() {
        config.preferred_gpu_capabilities = vec!["gpu".to_string(), "compute".to_string()];
    }

    Ok(Some(config))
}

#[derive(Debug, Clone)]
struct ImageParts {
    normalized: String,
    registry: String,
    repository: String,
}

impl ImageParts {
    fn parse(value: &str) -> Option<Self> {
        let normalized = value.trim().to_ascii_lowercase();
        let (registry, rest) = normalized.split_once('/')?;
        let registry = registry.to_string();
        let repository = rest
            .split_once('@')
            .map(|(head, _)| head)
            .unwrap_or(rest)
            .split_once(':')
            .map(|(head, _)| head)
            .unwrap_or(rest)
            .to_string();
        Some(Self {
            normalized,
            registry,
            repository,
        })
    }
}

impl KnowledgeImageMatch {
    fn matches(&self, image: &ImageParts) -> bool {
        let registry_match = self.registries.is_empty()
            || self
                .registries
                .iter()
                .any(|value| value.eq_ignore_ascii_case(&image.registry));
        let repository_match = self.repositories.is_empty()
            || self
                .repositories
                .iter()
                .any(|value| value.eq_ignore_ascii_case(&image.repository));
        let prefix_match = self.image_prefixes.is_empty()
            || self
                .image_prefixes
                .iter()
                .any(|prefix| image.normalized.starts_with(&prefix.to_ascii_lowercase()));
        registry_match && repository_match && prefix_match
    }
}

#[cfg(test)]
mod tests {
    use super::researched_config_for_image;
    use crate::model::RuntimeSignatures;

    #[test]
    fn researched_config_for_postgres_returns_curated_env_defaults() {
        let config = researched_config_for_image(
            "docker.io/library/postgres:16.4-alpine",
            &RuntimeSignatures::default(),
        )
        .expect("knowledge lookup should succeed")
        .expect("postgres entry should exist");
        assert!(config
            .recommended_env
            .iter()
            .any(|item| item.key == "POSTGRES_PASSWORD" && item.required));
        assert_eq!(config.runtime_uid, Some(999));
    }
}
