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
            profile.docs_url.as_deref().unwrap_or("unknown")
        ));
        out.push_str(&format!(
            "  dockerfile: {}\n",
            profile.dockerfile_url.as_deref().unwrap_or("unknown")
        ));
        out.push_str(&format!(
            "digest: {}\n",
            profile.digest.as_deref().unwrap_or("unknown")
        ));
        out.push_str("runtime:\n");
        out.push_str(&format!(
            "  user: {}\n",
            profile.runtime.user.as_deref().unwrap_or("unknown")
        ));
        out.push_str(&format!(
            "  working_dir: {}\n",
            profile.runtime.working_dir.as_deref().unwrap_or("unknown")
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
        out.push_str("  oci:\n");
        out.push_str(&format!(
            "    source: {}\n",
            profile.runtime.oci.source.as_deref().unwrap_or("unknown")
        ));
        out.push_str(&format!(
            "    revision: {}\n",
            profile.runtime.oci.revision.as_deref().unwrap_or("unknown")
        ));
        out.push_str(&format!(
            "    licenses: {}\n",
            profile.runtime.oci.licenses.as_deref().unwrap_or("unknown")
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
                    source.digest.as_deref().unwrap_or("unknown")
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
