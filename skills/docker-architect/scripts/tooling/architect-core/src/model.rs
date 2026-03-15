//! Domain models for deterministic image inventory.

use std::collections::BTreeMap;

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
    /// URL to the source repository when provenance is known but Dockerfile path is not.
    #[serde(default)]
    pub source_repo_url: Option<String>,
    /// Content digest if discovered.
    #[serde(default)]
    pub digest: Option<String>,
    /// Digest of the image config blob discovered via registry-v2 config lookup.
    #[serde(default)]
    pub config_digest: Option<String>,
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
    /// Curated deterministic image knowledge merged into the profile.
    #[serde(default)]
    pub researched_config: ResearchedConfig,
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
#[serde(default)]
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
    /// Parsed environment variables from image config (`KEY=VALUE` format).
    pub env: Vec<EnvVar>,
    /// Exposed ports from image config (for example `8080/tcp`).
    pub exposed_ports: Vec<String>,
    /// Declared volume mount points from image config.
    pub volumes: Vec<String>,
    /// Stop signal configured in image config.
    pub stop_signal: Option<String>,
    /// Healthcheck settings from image config.
    pub healthcheck: Option<HealthcheckProfile>,
    /// Optional runtime tool availability populated by local probe runs.
    pub tools: BTreeMap<String, bool>,
    /// Detailed runtime tool probe results populated by local probe runs.
    #[serde(default)]
    pub tool_details: BTreeMap<String, RuntimeToolDetail>,
    /// Signature hints inferred from image config and curated knowledge.
    #[serde(default)]
    pub signatures: RuntimeSignatures,
    /// Selected OCI labels used for traceability.
    pub oci: OciLabelProfile,
}

/// Detailed runtime tool probe record.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct RuntimeToolDetail {
    /// Whether the tool was detected as runnable in the image.
    pub available: bool,
    /// Best-effort executable path in the image when discovered.
    pub path: Option<String>,
    /// Probe strategy that discovered the tool.
    pub strategy: Option<String>,
}

/// Runtime signature hints used by deterministic heuristics.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct RuntimeSignatures {
    /// Whether OpenCL-related markers were detected.
    pub opencl: bool,
    /// Whether NVIDIA runtime markers were detected.
    pub nvidia: bool,
    /// Whether ROCm runtime markers were detected.
    pub rocm: bool,
    /// Whether the image likely requires GPU/compute device access.
    pub gpu_compute: bool,
    /// Whether runtime probing indicates a shell-less/distroless image.
    pub distroless: bool,
}

/// One environment variable parsed from image config.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EnvVar {
    /// Environment variable key.
    pub key: String,
    /// Optional value for the key.
    #[serde(default)]
    pub value: Option<String>,
}

/// Image healthcheck data extracted from the config blob.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct HealthcheckProfile {
    /// Healthcheck test command tokens.
    pub test: Vec<String>,
    /// Healthcheck interval in nanoseconds.
    pub interval_ns: Option<u64>,
    /// Healthcheck timeout in nanoseconds.
    pub timeout_ns: Option<u64>,
    /// Healthcheck start period in nanoseconds.
    pub start_period_ns: Option<u64>,
    /// Healthcheck retries.
    pub retries: Option<u32>,
}

/// Selected OCI labels from image config.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct OciLabelProfile {
    /// OCI source URL label.
    pub source: Option<String>,
    /// OCI revision label.
    pub revision: Option<String>,
    /// OCI licenses label.
    pub licenses: Option<String>,
}

/// Curated, deterministic recommendations for a researched image.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct ResearchedConfig {
    /// Recommended environment variables discovered from curated image knowledge.
    pub recommended_env: Vec<RecommendedEnvVar>,
    /// Paths that should be mounted writable at runtime.
    pub required_mounts: Vec<String>,
    /// Security and hardening notes from curated image knowledge.
    pub security_notes: Vec<String>,
    /// Known runtime UID hint for deterministic permission init workflows.
    pub runtime_uid: Option<u32>,
    /// Known runtime GID hint for deterministic permission init workflows.
    pub runtime_gid: Option<u32>,
    /// Preferred healthcheck template for compose synthesis.
    pub preferred_healthcheck: Option<ComposeHealthcheckTemplate>,
    /// Preferred GPU driver when device reservation is required.
    pub preferred_gpu_driver: Option<String>,
    /// Preferred device capabilities when GPU reservation is required.
    pub preferred_gpu_capabilities: Vec<String>,
}

/// One recommended environment variable from curated image knowledge.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct RecommendedEnvVar {
    /// Environment variable key.
    pub key: String,
    /// Optional sane default value.
    pub default_value: Option<String>,
    /// Whether this variable should be treated as required by default.
    pub required: bool,
    /// Deterministic rationale for the recommendation.
    pub rationale: Option<String>,
}

/// Compose-oriented healthcheck template with string durations.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(default)]
pub struct ComposeHealthcheckTemplate {
    /// Healthcheck test command tokens.
    pub test: Vec<String>,
    /// Compose interval value such as `10s`.
    pub interval: Option<String>,
    /// Compose timeout value such as `5s`.
    pub timeout: Option<String>,
    /// Compose start period value such as `20s`.
    pub start_period: Option<String>,
    /// Compose retry count.
    pub retries: Option<u32>,
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

/// Resolve the runtime user for a profile using image config first, then curated UID/GID hints.
pub(crate) fn resolved_runtime_user_for_profile(profile: &ImageProfile) -> Option<String> {
    if let Some(user) = profile.runtime.user.as_deref().map(str::trim) {
        if runtime_user_value_is_resolved(user) {
            return Some(user.to_string());
        }
    }

    match (
        profile.researched_config.runtime_uid,
        profile.researched_config.runtime_gid,
    ) {
        (Some(uid), Some(gid)) => Some(format!("{uid}:{gid}")),
        (Some(uid), None) => Some(uid.to_string()),
        (None, Some(_)) | (None, None) => None,
    }
}

fn runtime_user_value_is_resolved(user: &str) -> bool {
    !user.is_empty() && !user.eq_ignore_ascii_case("unknown")
}
