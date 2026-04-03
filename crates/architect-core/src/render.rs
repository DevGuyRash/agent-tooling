//! Deterministic renderers.

use crate::model::CachedProfiles;

/// Render cached profiles as markdown blocks.
///
/// # Arguments
/// * `cache` - Parsed cache structure.
///
/// # Returns
/// * Markdown suitable for inclusion in skill output.
///
/// # Examples
/// ```
/// use architect_core::model::CachedProfiles;
/// use architect_core::render::render_markdown;
///
/// let markdown = render_markdown(&CachedProfiles {
///     schema_version: 2,
///     profiles: Vec::new(),
///     unresolved_references: Vec::new(),
/// });
/// assert!(markdown.contains("Traceability"));
/// ```
pub fn render_markdown(cache: &CachedProfiles) -> String {
    let mut out = String::new();
    if !cache.unresolved_references.is_empty() {
        out.push_str("#### Unresolved Image References\n");
        out.push_str("```yaml\n");
        out.push_str("unresolved:\n");
        for reference in &cache.unresolved_references {
            out.push_str(&format!("  - {}\n", reference));
        }
        out.push_str("```\n\n");
    }

    for profile in &cache.profiles {
        out.push_str(&format!("#### {}\n", profile.id));
        out.push_str("```yaml\n");
        out.push_str(&format!("id: {}\n", profile.id));
        out.push_str(&format!("image: {}\n", profile.image));
        out.push_str("source:\n");
        out.push_str(&format!(
            "  docs: {}\n",
            profile.docs_url.as_deref().map_or("unknown", |value| value)
        ));
        out.push_str(&format!(
            "  dockerfile: {}\n",
            profile
                .dockerfile_url
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str(&format!(
            "  repo: {}\n",
            profile
                .source_repo_url
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str(&format!("  provenance: {}\n", classify_provenance(profile)));
        out.push_str(&format!(
            "digest: {}\n",
            profile.digest.as_deref().map_or("unknown", |value| value)
        ));
        out.push_str(&format!(
            "config_digest: {}\n",
            profile
                .config_digest
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str("runtime:\n");
        out.push_str(&format!(
            "  user: {}\n",
            profile
                .runtime
                .user
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str(&format!(
            "  working_dir: {}\n",
            profile
                .runtime
                .working_dir
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str("  entrypoint:\n");
        if profile.runtime.entrypoint.is_empty() {
            out.push_str("    - unknown\n");
        } else {
            for token in &profile.runtime.entrypoint {
                out.push_str(&format!("    - {}\n", token));
            }
        }
        out.push_str("  cmd:\n");
        if profile.runtime.cmd.is_empty() {
            out.push_str("    - unknown\n");
        } else {
            for token in &profile.runtime.cmd {
                out.push_str(&format!("    - {}\n", token));
            }
        }
        out.push_str("  env_keys:\n");
        if profile.runtime.env_keys.is_empty() {
            out.push_str("    - none\n");
        } else {
            for key in &profile.runtime.env_keys {
                out.push_str(&format!("    - {}\n", key));
            }
        }
        out.push_str("  env:\n");
        if profile.runtime.env.is_empty() {
            out.push_str("    - none\n");
        } else {
            for item in &profile.runtime.env {
                match item.value.as_deref() {
                    Some(value) => out.push_str(&format!("    - {}={}\n", item.key, value)),
                    None => out.push_str(&format!("    - {}\n", item.key)),
                }
            }
        }
        out.push_str("  exposed_ports:\n");
        if profile.runtime.exposed_ports.is_empty() {
            out.push_str("    - none\n");
        } else {
            for port in &profile.runtime.exposed_ports {
                out.push_str(&format!("    - {}\n", port));
            }
        }
        out.push_str("  volumes:\n");
        if profile.runtime.volumes.is_empty() {
            out.push_str("    - none\n");
        } else {
            for volume in &profile.runtime.volumes {
                out.push_str(&format!("    - {}\n", volume));
            }
        }
        out.push_str(&format!(
            "  stop_signal: {}\n",
            profile
                .runtime
                .stop_signal
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str("  healthcheck:\n");
        if let Some(healthcheck) = &profile.runtime.healthcheck {
            out.push_str("    test:\n");
            if healthcheck.test.is_empty() {
                out.push_str("      - none\n");
            } else {
                for token in &healthcheck.test {
                    out.push_str(&format!("      - {}\n", token));
                }
            }
            out.push_str(&format!(
                "    interval_ns: {}\n",
                healthcheck
                    .interval_ns
                    .map_or_else(|| "unknown".to_string(), |value| value.to_string())
            ));
            out.push_str(&format!(
                "    timeout_ns: {}\n",
                healthcheck
                    .timeout_ns
                    .map_or_else(|| "unknown".to_string(), |value| value.to_string())
            ));
            out.push_str(&format!(
                "    start_period_ns: {}\n",
                healthcheck
                    .start_period_ns
                    .map_or_else(|| "unknown".to_string(), |value| value.to_string())
            ));
            out.push_str(&format!(
                "    retries: {}\n",
                healthcheck
                    .retries
                    .map_or_else(|| "unknown".to_string(), |value| value.to_string())
            ));
        } else {
            out.push_str("    test:\n");
            out.push_str("      - none\n");
            out.push_str("    interval_ns: unknown\n");
            out.push_str("    timeout_ns: unknown\n");
            out.push_str("    start_period_ns: unknown\n");
            out.push_str("    retries: unknown\n");
        }
        out.push_str("  tools:\n");
        if profile.runtime.tools.is_empty() {
            out.push_str("    - none\n");
        } else {
            for (tool, available) in &profile.runtime.tools {
                out.push_str(&format!("    - {}: {}\n", tool, available));
            }
        }
        out.push_str("  tool_details:\n");
        if profile.runtime.tool_details.is_empty() {
            out.push_str("    - none\n");
        } else {
            for (tool, detail) in &profile.runtime.tool_details {
                out.push_str(&format!(
                    "    - {}: available={}, path={}, strategy={}\n",
                    tool,
                    detail.available,
                    detail.path.as_deref().map_or("unknown", |value| value),
                    detail.strategy.as_deref().map_or("unknown", |value| value)
                ));
            }
        }
        out.push_str("  signatures:\n");
        out.push_str(&format!(
            "    opencl: {}\n",
            profile.runtime.signatures.opencl
        ));
        out.push_str(&format!(
            "    nvidia: {}\n",
            profile.runtime.signatures.nvidia
        ));
        out.push_str(&format!("    rocm: {}\n", profile.runtime.signatures.rocm));
        out.push_str(&format!(
            "    gpu_compute: {}\n",
            profile.runtime.signatures.gpu_compute
        ));
        out.push_str(&format!(
            "    distroless: {}\n",
            profile.runtime.signatures.distroless
        ));
        out.push_str("  oci:\n");
        out.push_str(&format!(
            "    source: {}\n",
            profile
                .runtime
                .oci
                .source
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str(&format!(
            "    revision: {}\n",
            profile
                .runtime
                .oci
                .revision
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str(&format!(
            "    licenses: {}\n",
            profile
                .runtime
                .oci
                .licenses
                .as_deref()
                .map_or("unknown", |value| value)
        ));
        out.push_str("platforms:\n");
        if profile.platforms.is_empty() {
            out.push_str("  - os: unknown\n");
            out.push_str("    arch: unknown\n");
        } else {
            for platform in &profile.platforms {
                out.push_str(&format!("  - os: {}\n", platform.os));
                out.push_str(&format!("    arch: {}\n", platform.arch));
            }
        }
        out.push_str("sources:\n");
        if profile.sources.is_empty() {
            out.push_str("  - kind: unknown\n");
            out.push_str("    url: unknown\n");
            out.push_str("    status: unknown\n");
        } else {
            for source in &profile.sources {
                out.push_str(&format!("  - kind: {}\n", source.kind));
                out.push_str(&format!("    url: {}\n", source.url));
                out.push_str(&format!("    status: {}\n", source.status));
                out.push_str(&format!(
                    "    digest: {}\n",
                    source.digest.as_deref().map_or("unknown", |value| value)
                ));
            }
        }
        out.push_str("notes:\n");
        if profile.notes.is_empty() {
            out.push_str("  - none\n");
        } else {
            for note in &profile.notes {
                out.push_str(&format!("  - {}\n", note));
            }
        }
        out.push_str("researched_config:\n");
        out.push_str("  recommended_env:\n");
        if profile.researched_config.recommended_env.is_empty() {
            out.push_str("    - none\n");
        } else {
            for item in &profile.researched_config.recommended_env {
                out.push_str(&format!("    - key: {}\n", item.key));
                out.push_str(&format!(
                    "      default_value: {}\n",
                    item.default_value.as_deref().map_or("none", |value| value)
                ));
                out.push_str(&format!("      required: {}\n", item.required));
                out.push_str(&format!(
                    "      rationale: {}\n",
                    item.rationale.as_deref().map_or("none", |value| value)
                ));
            }
        }
        out.push_str("  required_mounts:\n");
        if profile.researched_config.required_mounts.is_empty() {
            out.push_str("    - none\n");
        } else {
            for path in &profile.researched_config.required_mounts {
                out.push_str(&format!("    - {}\n", path));
            }
        }
        out.push_str(&format!(
            "  runtime_uid: {}\n",
            profile
                .researched_config
                .runtime_uid
                .map_or_else(|| "unknown".to_string(), |value| value.to_string())
        ));
        out.push_str(&format!(
            "  runtime_gid: {}\n",
            profile
                .researched_config
                .runtime_gid
                .map_or_else(|| "unknown".to_string(), |value| value.to_string())
        ));
        out.push_str("  security_notes:\n");
        if profile.researched_config.security_notes.is_empty() {
            out.push_str("    - none\n");
        } else {
            for note in &profile.researched_config.security_notes {
                out.push_str(&format!("    - {}\n", note));
            }
        }
        out.push_str("```\n\n");
    }

    let ids: Vec<&str> = cache
        .profiles
        .iter()
        .map(|profile| profile.id.as_str())
        .collect();
    out.push_str(&format!(
        "Traceability: {}; unresolved:{}; O-1.\n",
        ids.join(", "),
        cache.unresolved_references.len()
    ));
    out
}

fn classify_provenance(profile: &crate::model::ImageProfile) -> &'static str {
    if profile.source_repo_url.is_some()
        || profile.runtime.oci.source.is_some()
        || profile
            .sources
            .iter()
            .any(|source| source.kind == "registry-v2-config" && source.status == "ok")
    {
        return "deterministic";
    }

    if profile.researched_config.runtime_uid.is_some()
        || profile.researched_config.runtime_gid.is_some()
        || !profile.researched_config.recommended_env.is_empty()
        || !profile.researched_config.required_mounts.is_empty()
        || !profile.researched_config.security_notes.is_empty()
        || profile.researched_config.preferred_healthcheck.is_some()
        || profile.researched_config.preferred_gpu_driver.is_some()
        || !profile
            .researched_config
            .preferred_gpu_capabilities
            .is_empty()
    {
        return "curated";
    }

    "ambiguous"
}

/// Render cached profiles as pretty JSON.
///
/// # Arguments
/// * `cache` - Parsed cache structure.
///
/// # Returns
/// * `Ok(String)` pretty-printed JSON text when serialization succeeds.
/// * `Err(serde_json::Error)` when serialization fails.
pub fn render_json(cache: &CachedProfiles) -> Result<String, serde_json::Error> {
    serde_json::to_string_pretty(cache)
}
