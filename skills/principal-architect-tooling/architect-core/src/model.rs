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
    pub docs_url: Option<String>,
    /// URL to source Dockerfile or source repository.
    pub dockerfile_url: Option<String>,
    /// Content digest if discovered.
    pub digest: Option<String>,
    /// Platforms reported by API.
    pub platforms: Vec<Platform>,
    /// Writeable notes or caveats.
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

/// Wire cache format.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CachedProfiles {
    /// Schema version used by validators.
    pub schema_version: u32,
    /// Profile records.
    pub profiles: Vec<ImageProfile>,
}
