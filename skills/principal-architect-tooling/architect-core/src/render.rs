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
/// let markdown = render_markdown(&CachedProfiles { schema_version: 1, profiles: Vec::new() });
/// assert!(markdown.contains("Traceability"));
/// ```
pub fn render_markdown(cache: &CachedProfiles) -> String {
    let mut out = String::new();
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
    out.push_str(&format!("Traceability: {}; O-1.\n", ids.join(", ")));
    out
}

/// Render cached profiles as pretty JSON.
///
/// # Arguments
/// * `cache` - Parsed cache structure.
///
/// # Returns
/// * Pretty-printed JSON text.
pub fn render_json(cache: &CachedProfiles) -> String {
    match serde_json::to_string_pretty(cache) {
        Ok(value) => value,
        Err(_) => "{}".to_string(),
    }
}
