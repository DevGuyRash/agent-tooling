//! Domain models for deterministic image inventory.

use serde::{Deserialize, Serialize};

/// Output profile for one researched image.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ImageProfile {
    /// Stable traceability ID such as `IMG-1`.
    pub id: String,
    /// Fully qualified image reference with tag and optional digest.
    pub image: String,
    /// URL to primary documentation.
    #[serde(default)]
    pub docs_url: Option<String>,
    /// URL to source Dockerfile or source repository.
    #[serde(default)]
    pub dockerfile_url: Option<String>,
    /// Content digest if discovered.
    #[serde(default)]
    pub digest: Option<String>,
    /// Platforms reported by API.
    #[serde(default)]
    pub platforms: Vec<Platform>,
    /// Runtime-relevant settings extracted from image config.
    #[serde(default)]
    pub runtime: RuntimeProfile,
    /// Structured source records used to build deterministic research output.
    #[serde(default)]
    pub sources: Vec<SourceRecord>,
    /// Human-readable notes or caveats.
    #[serde(default)]
    pub notes: Vec<String>,
}

/// Platform entry.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Platform {
    /// OS field, usually linux.
    pub os: String,
    /// CPU architecture.
    pub arch: String,
}

/// Runtime settings extracted from the image config blob.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct RuntimeProfile {
    /// Default runtime user for the image config.
    pub user: Option<String>,
    /// Entrypoint configured in the image.
    pub entrypoint: Vec<String>,
    /// Default command configured in the image.
    pub cmd: Vec<String>,
    /// Working directory configured in the image.
    pub working_dir: Option<String>,
    /// Environment variable keys present in the image config.
    pub env_keys: Vec<String>,
    /// Selected OCI labels used for traceability.
    pub oci: OciLabelProfile,
}

/// Selected OCI labels from image config.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct OciLabelProfile {
    /// OCI source URL label.
    pub source: Option<String>,
    /// OCI revision label.
    pub revision: Option<String>,
    /// OCI licenses label.
    pub licenses: Option<String>,
}

/// Structured source metadata entry.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SourceRecord {
    /// Stable source kind, for example `registry-v2` or `docker-hub-api`.
    pub kind: String,
    /// Source URL accessed by the fetcher.
    pub url: String,
    /// Outcome status for the source request.
    pub status: String,
    /// Optional digest reported by the source.
    pub digest: Option<String>,
}

/// Wire cache format.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CachedProfiles {
    /// Schema version used by validators.
    pub schema_version: u32,
    /// Profile records.
    #[serde(default)]
    pub profiles: Vec<ImageProfile>,
    /// Image references that could not be deterministically resolved.
    #[serde(default)]
    pub unresolved_references: Vec<String>,
}
