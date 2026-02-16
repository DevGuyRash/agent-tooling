//! Deterministic compose generator that emits YAML anchors for reusable hardened fragments.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use serde::Deserialize;
use serde_yaml::{Mapping, Value as YamlValue};

use crate::anchor_suggest;
use crate::error::AppError;
use crate::heuristics::DeployMode;

const BUILTIN_DEFAULTS_V1: &str =
    include_str!("../../../../references/compose-defaults/defaults.v1.yaml");
const MAX_GENERATOR_COMPOSITES: usize = 200;

/// Anchor rendering mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnchorMode {
    /// Include reusable anchors when usage reaches threshold (default).
    Auto,
    /// Emit only the core hardening anchor and inline everything else.
    Minimal,
    /// Emit all relevant anchors, even when used by a single service.
    Full,
}

impl AnchorMode {
    /// Parse an anchor mode string.
    pub fn parse(value: &str) -> Result<Self, AppError> {
        match value {
            "auto" => Ok(Self::Auto),
            "minimal" => Ok(Self::Minimal),
            "full" => Ok(Self::Full),
            _ => Err(AppError::InvalidInput {
                reason: format!("unsupported anchor mode: {value}"),
            }),
        }
    }
}

/// Generate an anchorized compose yaml document from an already-hardened compose yaml input.
///
/// # Arguments
/// * `hardened_yaml` - Compose YAML after policy patching/hardening.
/// * `mode` - Deployment mode for mode-specific anchor fragments.
/// * `anchor_mode` - Anchor inclusion strategy.
/// * `defaults_file` - Optional custom defaults yaml path.
///
/// # Returns
/// * `Ok(String)` with deterministic anchorized compose yaml.
/// * `Err(AppError)` when parsing or rendering fails.
pub fn generate_anchored_compose(
    hardened_yaml: &str,
    mode: DeployMode,
    anchor_mode: AnchorMode,
    defaults_file: Option<&Path>,
) -> Result<String, AppError> {
    let mut document: YamlValue =
        serde_yaml::from_str(hardened_yaml).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse hardened compose yaml: {error}"),
        })?;
    let root = document
        .as_mapping_mut()
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose root must be a mapping".to_string(),
        })?;
    let services = root
        .get(YamlValue::String("services".to_string()))
        .and_then(YamlValue::as_mapping)
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose input must include a services mapping".to_string(),
        })?;

    let defaults = load_defaults(defaults_file)?;
    let applicable = filter_defaults_for_mode(&defaults, mode);
    let service_model = plan_service_anchors(services, &applicable, anchor_mode)?;

    render_anchorized_compose(root, &service_model)
}

#[derive(Debug, Clone, Deserialize)]
struct DefaultsDocument {
    version: u32,
    #[serde(default)]
    anchors: Vec<RawAnchorDefinition>,
}

#[derive(Debug, Clone, Deserialize)]
struct RawAnchorDefinition {
    name: String,
    yaml_key: String,
    mode: AnchorScope,
    #[serde(default = "default_min_usage")]
    min_usage: usize,
    body: YamlValue,
}

#[derive(Debug, Clone)]
struct AnchorDefinition {
    name: String,
    yaml_key: String,
    mode: AnchorScope,
    min_usage: usize,
    body: YamlValue,
    source: AnchorSource,
    key_count: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AnchorSource {
    Defaults,
    Composite,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "lowercase")]
enum AnchorScope {
    #[default]
    Any,
    Compose,
    Swarm,
}

#[derive(Debug, Clone)]
struct ServiceAnchorRender {
    selected_anchors: Vec<String>,
    rendered_mapping: Mapping,
}

#[derive(Debug, Clone)]
struct AnchorPlan {
    selected_anchor_defs: BTreeMap<String, AnchorDefinition>,
    services: BTreeMap<String, ServiceAnchorRender>,
}

fn default_min_usage() -> usize {
    2
}

fn load_defaults(custom_defaults_file: Option<&Path>) -> Result<Vec<AnchorDefinition>, AppError> {
    let mut defaults = parse_defaults_document(BUILTIN_DEFAULTS_V1)?;
    if let Some(path) = custom_defaults_file {
        let content =
            fs::read_to_string(path).map_err(|error| AppError::io(path, error.to_string()))?;
        let custom = parse_defaults_document(&content)?;
        let mut by_name: BTreeMap<String, AnchorDefinition> = defaults
            .into_iter()
            .map(|entry| (entry.name.clone(), entry))
            .collect();
        for entry in custom {
            by_name.insert(entry.name.clone(), entry);
        }
        defaults = by_name.into_values().collect();
    }
    defaults.sort_by(|left, right| left.yaml_key.cmp(&right.yaml_key));
    Ok(defaults)
}

fn parse_defaults_document(content: &str) -> Result<Vec<AnchorDefinition>, AppError> {
    let document: DefaultsDocument =
        serde_yaml::from_str(content).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse compose defaults yaml: {error}"),
        })?;
    if document.version != 1 {
        return Err(AppError::InvalidInput {
            reason: format!(
                "unsupported compose defaults schema version: {}",
                document.version
            ),
        });
    }

    let mut names = BTreeSet::new();
    let mut yaml_keys = BTreeSet::new();
    let mut output = Vec::new();
    for raw in document.anchors {
        if !names.insert(raw.name.clone()) {
            return Err(AppError::InvalidInput {
                reason: format!("duplicate compose defaults anchor name: {}", raw.name),
            });
        }
        if !yaml_keys.insert(raw.yaml_key.clone()) {
            return Err(AppError::InvalidInput {
                reason: format!("duplicate compose defaults yaml key: {}", raw.yaml_key),
            });
        }
        if !raw.yaml_key.starts_with("x-") {
            return Err(AppError::InvalidInput {
                reason: format!(
                    "compose defaults yaml key must start with `x-`: {}",
                    raw.yaml_key
                ),
            });
        }

        output.push(AnchorDefinition {
            key_count: key_count_for_body(&raw.body),
            name: raw.name,
            yaml_key: raw.yaml_key,
            mode: raw.mode,
            min_usage: raw.min_usage,
            body: raw.body,
            source: AnchorSource::Defaults,
        });
    }

    Ok(output)
}

fn key_count_for_body(body: &YamlValue) -> usize {
    body.as_mapping().map(Mapping::len).unwrap_or(1).max(1)
}

fn filter_defaults_for_mode(
    defaults: &[AnchorDefinition],
    mode: DeployMode,
) -> Vec<AnchorDefinition> {
    let mut filtered: Vec<AnchorDefinition> = defaults
        .iter()
        .filter(|item| {
            matches!(
                (item.mode.clone(), mode),
                (AnchorScope::Any, _)
                    | (AnchorScope::Compose, DeployMode::Compose)
                    | (AnchorScope::Swarm, DeployMode::Swarm)
            )
        })
        .cloned()
        .collect();
    filtered.sort_by(|left, right| left.yaml_key.cmp(&right.yaml_key));
    filtered
}

fn plan_service_anchors(
    services: &Mapping,
    defaults: &[AnchorDefinition],
    anchor_mode: AnchorMode,
) -> Result<AnchorPlan, AppError> {
    let mut service_names: Vec<String> = services
        .keys()
        .filter_map(YamlValue::as_str)
        .map(ToOwned::to_owned)
        .collect();
    service_names.sort();

    let mut applicability: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut usage_counts: BTreeMap<String, usize> = BTreeMap::new();

    // O(n * m) where n = number of services and m = number of candidate anchor defs.
    for service_name in &service_names {
        let service = services
            .get(YamlValue::String(service_name.clone()))
            .and_then(YamlValue::as_mapping)
            .ok_or_else(|| AppError::InvalidInput {
                reason: format!("service {service_name} must be a mapping"),
            })?;
        for definition in defaults {
            if anchor_matches_service(service, &definition.body) {
                applicability
                    .entry(service_name.clone())
                    .or_default()
                    .push(definition.name.clone());
                let counter = usage_counts.entry(definition.name.clone()).or_insert(0);
                *counter += 1;
            }
        }
    }

    let selected_names = select_default_anchor_names(defaults, &usage_counts, anchor_mode);
    let mut selected_defs = BTreeMap::new();
    for definition in defaults {
        if selected_names.contains(&definition.name) {
            selected_defs.insert(definition.name.clone(), definition.clone());
        }
    }

    let mut services_render = BTreeMap::new();
    let mut service_covered_keys: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for service_name in &service_names {
        let original = services
            .get(YamlValue::String(service_name.clone()))
            .and_then(YamlValue::as_mapping)
            .ok_or_else(|| AppError::InvalidInput {
                reason: format!("service {service_name} must be a mapping"),
            })?;
        let mut rendered = original.clone();
        let selected_for_service: Vec<String> = applicability
            .get(service_name)
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .filter(|name| selected_names.contains(name))
            .collect();

        let mut covered = BTreeSet::new();
        for anchor_name in &selected_for_service {
            let Some(definition) = selected_defs.get(anchor_name) else {
                continue;
            };
            strip_covered_fields(&mut rendered, &definition.body);
            for key in top_level_keys(&definition.body) {
                covered.insert(key);
            }
        }
        service_covered_keys.insert(service_name.clone(), covered);

        services_render.insert(
            service_name.clone(),
            ServiceAnchorRender {
                selected_anchors: selected_for_service,
                rendered_mapping: rendered,
            },
        );
    }

    if anchor_mode != AnchorMode::Minimal {
        let threshold = composite_threshold(service_names.len(), anchor_mode);
        if threshold >= 2 {
            let residual_services = service_mapping_from_rendered(&services_render);
            let mut composites = anchor_suggest::discover_composite_anchors(
                &residual_services,
                threshold,
                MAX_GENERATOR_COMPOSITES,
            )?;
            composites.sort_by(|left, right| {
                (
                    std::cmp::Reverse(left.key_count),
                    std::cmp::Reverse(left.usage_count),
                    left.yaml_key.as_str(),
                )
                    .cmp(&(
                        std::cmp::Reverse(right.key_count),
                        std::cmp::Reverse(right.usage_count),
                        right.yaml_key.as_str(),
                    ))
            });

            for candidate in composites {
                if selected_defs.contains_key(&candidate.name)
                    || selected_defs
                        .values()
                        .any(|definition| definition.yaml_key == candidate.yaml_key)
                {
                    continue;
                }

                let candidate_keys: BTreeSet<String> = top_level_keys(&candidate.body).into_iter().collect();
                if candidate_keys.len() < 2 {
                    continue;
                }

                let conflicts = candidate.service_names.iter().any(|service_name| {
                    service_covered_keys.get(service_name).is_some_and(|covered| {
                        candidate_keys.iter().any(|key| covered.contains(key))
                    })
                });
                if conflicts {
                    continue;
                }

                let definition = AnchorDefinition {
                    key_count: candidate.key_count,
                    name: candidate.name.clone(),
                    yaml_key: candidate.yaml_key,
                    mode: AnchorScope::Any,
                    min_usage: threshold,
                    body: candidate.body,
                    source: AnchorSource::Composite,
                };

                for service_name in &candidate.service_names {
                    let Some(service_render) = services_render.get_mut(service_name) else {
                        continue;
                    };
                    service_render.selected_anchors.push(definition.name.clone());
                    strip_covered_fields(&mut service_render.rendered_mapping, &definition.body);

                    let covered = service_covered_keys.entry(service_name.clone()).or_default();
                    for key in &candidate_keys {
                        covered.insert(key.clone());
                    }
                }

                selected_defs.insert(definition.name.clone(), definition);
            }
        }
    }

    for service_render in services_render.values_mut() {
        service_render
            .selected_anchors
            .sort_by(|left, right| compare_anchor_names(left, right, &selected_defs));
        service_render.selected_anchors.dedup();
    }

    Ok(AnchorPlan {
        selected_anchor_defs: selected_defs,
        services: services_render,
    })
}

fn service_mapping_from_rendered(services_render: &BTreeMap<String, ServiceAnchorRender>) -> Mapping {
    let mut services = Mapping::new();
    for (name, render) in services_render {
        services.insert(
            YamlValue::String(name.clone()),
            YamlValue::Mapping(render.rendered_mapping.clone()),
        );
    }
    services
}

fn composite_threshold(service_count: usize, anchor_mode: AnchorMode) -> usize {
    match anchor_mode {
        AnchorMode::Minimal => usize::MAX,
        AnchorMode::Full => 2,
        AnchorMode::Auto => adaptive_threshold(service_count),
    }
}

fn adaptive_threshold(service_count: usize) -> usize {
    if service_count > 5 {
        3
    } else {
        2
    }
}

fn select_default_anchor_names(
    defaults: &[AnchorDefinition],
    usage_counts: &BTreeMap<String, usize>,
    mode: AnchorMode,
) -> BTreeSet<String> {
    let mut selected = BTreeSet::new();
    for definition in defaults {
        let usage = usage_counts.get(&definition.name).copied().unwrap_or(0);
        let should_include = match mode {
            AnchorMode::Full => usage > 0,
            AnchorMode::Minimal => definition.name == "hardening_core" && usage > 0,
            AnchorMode::Auto => usage >= definition.min_usage,
        };
        if should_include {
            selected.insert(definition.name.clone());
        }
    }
    selected
}

fn top_level_keys(body: &YamlValue) -> Vec<String> {
    let mut keys: Vec<String> = body
        .as_mapping()
        .map(|map| {
            map.keys()
                .filter_map(YamlValue::as_str)
                .map(ToOwned::to_owned)
                .collect::<Vec<String>>()
        })
        .unwrap_or_default();
    keys.sort();
    keys
}

fn anchor_matches_service(service: &Mapping, body: &YamlValue) -> bool {
    let Some(anchor_map) = body.as_mapping() else {
        return false;
    };
    for (key, expected) in anchor_map {
        let Some(actual) = service.get(key) else {
            return false;
        };
        if actual != expected {
            return false;
        }
    }
    true
}

fn strip_covered_fields(service: &mut Mapping, body: &YamlValue) {
    let Some(anchor_map) = body.as_mapping() else {
        return;
    };
    for (key, expected) in anchor_map {
        if service.get(key).is_some_and(|actual| actual == expected) {
            let _ = service.remove(key);
        }
    }
}

fn compare_anchor_names(
    left: &str,
    right: &str,
    defs: &BTreeMap<String, AnchorDefinition>,
) -> std::cmp::Ordering {
    let left_def = defs.get(left);
    let right_def = defs.get(right);

    let left_rank = left_def.map(anchor_source_rank).unwrap_or(2);
    let right_rank = right_def.map(anchor_source_rank).unwrap_or(2);
    if left_rank != right_rank {
        return left_rank.cmp(&right_rank);
    }

    let left_composite_key_count = left_def
        .filter(|definition| definition.source == AnchorSource::Composite)
        .map(|definition| definition.key_count)
        .unwrap_or(0);
    let right_composite_key_count = right_def
        .filter(|definition| definition.source == AnchorSource::Composite)
        .map(|definition| definition.key_count)
        .unwrap_or(0);
    if left_composite_key_count != right_composite_key_count {
        return right_composite_key_count.cmp(&left_composite_key_count);
    }

    let left_yaml = left_def.map(|definition| definition.yaml_key.as_str()).unwrap_or(left);
    let right_yaml = right_def
        .map(|definition| definition.yaml_key.as_str())
        .unwrap_or(right);

    (left_yaml, left).cmp(&(right_yaml, right))
}

fn anchor_source_rank(definition: &AnchorDefinition) -> u8 {
    match definition.source {
        AnchorSource::Defaults => 0,
        AnchorSource::Composite => 1,
    }
}

fn render_anchorized_compose(root: &Mapping, plan: &AnchorPlan) -> Result<String, AppError> {
    let mut lines = Vec::new();
    let mut selected_defs: Vec<&AnchorDefinition> = plan.selected_anchor_defs.values().collect();
    selected_defs.sort_by(|left, right| compare_anchor_defs(left, right));

    for definition in &selected_defs {
        lines.push(format!("{}: &{}", definition.yaml_key, definition.name));
        emit_value(&definition.body, 2, &mut lines)?;
    }

    lines.push("services:".to_string());
    for (service_name, service_render) in &plan.services {
        lines.push(format!("  {service_name}:"));
        match service_render.selected_anchors.len() {
            0 => {}
            1 => {
                let anchor = &service_render.selected_anchors[0];
                lines.push(format!("    <<: *{anchor}"));
            }
            _ => {
                let aliases = service_render
                    .selected_anchors
                    .iter()
                    .map(|anchor| format!("*{anchor}"))
                    .collect::<Vec<String>>()
                    .join(", ");
                lines.push(format!("    <<: [{aliases}]"));
            }
        }
        emit_mapping_entries(&service_render.rendered_mapping, 4, &mut lines)?;
    }

    let mut top_level_entries: Vec<(String, &YamlValue)> = root
        .iter()
        .filter_map(|(key, value)| {
            key.as_str()
                .map(|text| (text.to_string(), value))
                .filter(|(text, _)| text != "services")
        })
        .collect();
    top_level_entries.sort_by(|left, right| left.0.cmp(&right.0));
    for (key, value) in top_level_entries {
        if selected_defs
            .iter()
            .any(|definition| definition.yaml_key == key)
        {
            continue;
        }
        emit_key_value(&key, value, 0, &mut lines)?;
    }

    Ok(format!("{}\n", lines.join("\n")))
}

fn compare_anchor_defs(left: &AnchorDefinition, right: &AnchorDefinition) -> std::cmp::Ordering {
    (
        anchor_source_rank(left),
        std::cmp::Reverse(left.key_count),
        left.yaml_key.as_str(),
        left.name.as_str(),
    )
        .cmp(&(
            anchor_source_rank(right),
            std::cmp::Reverse(right.key_count),
            right.yaml_key.as_str(),
            right.name.as_str(),
        ))
}

fn emit_value(value: &YamlValue, indent: usize, lines: &mut Vec<String>) -> Result<(), AppError> {
    match value {
        YamlValue::Mapping(map) => emit_mapping_entries(map, indent, lines),
        YamlValue::Sequence(sequence) => emit_sequence(sequence, indent, lines),
        _ => {
            lines.push(format!("{}{}", spaces(indent), format_scalar(value)?));
            Ok(())
        }
    }
}

fn emit_mapping_entries(
    mapping: &Mapping,
    indent: usize,
    lines: &mut Vec<String>,
) -> Result<(), AppError> {
    let mut entries: Vec<(String, &YamlValue)> = mapping
        .iter()
        .filter_map(|(key, value)| key.as_str().map(|text| (text.to_string(), value)))
        .collect();
    entries.sort_by(|left, right| left.0.cmp(&right.0));
    for (key, value) in entries {
        emit_key_value(&key, value, indent, lines)?;
    }
    Ok(())
}

fn emit_key_value(
    key: &str,
    value: &YamlValue,
    indent: usize,
    lines: &mut Vec<String>,
) -> Result<(), AppError> {
    match value {
        YamlValue::Mapping(map) => {
            if map.is_empty() {
                lines.push(format!("{}{}: {{}}", spaces(indent), key));
            } else {
                lines.push(format!("{}{}:", spaces(indent), key));
                emit_mapping_entries(map, indent + 2, lines)?;
            }
        }
        YamlValue::Sequence(sequence) => {
            if sequence.is_empty() {
                lines.push(format!("{}{}: []", spaces(indent), key));
            } else {
                lines.push(format!("{}{}:", spaces(indent), key));
                emit_sequence(sequence, indent + 2, lines)?;
            }
        }
        _ => {
            lines.push(format!(
                "{}{}: {}",
                spaces(indent),
                key,
                format_scalar(value)?
            ));
        }
    }
    Ok(())
}

fn emit_sequence(
    sequence: &[YamlValue],
    indent: usize,
    lines: &mut Vec<String>,
) -> Result<(), AppError> {
    for item in sequence {
        match item {
            YamlValue::Mapping(map) => {
                lines.push(format!("{}-", spaces(indent)));
                emit_mapping_entries(map, indent + 2, lines)?;
            }
            YamlValue::Sequence(nested) => {
                lines.push(format!("{}-", spaces(indent)));
                emit_sequence(nested, indent + 2, lines)?;
            }
            _ => lines.push(format!("{}- {}", spaces(indent), format_scalar(item)?)),
        }
    }
    Ok(())
}

fn format_scalar(value: &YamlValue) -> Result<String, AppError> {
    if let YamlValue::String(text) = value {
        if text.contains('\n') {
            return serde_json::to_string(text).map_err(|error| AppError::InvalidInput {
                reason: format!("failed to encode multiline scalar as json string: {error}"),
            });
        }
    }

    let mut serialized = serde_yaml::to_string(value).map_err(|error| AppError::InvalidInput {
        reason: format!("failed to serialize yaml scalar: {error}"),
    })?;
    if let Some(stripped) = serialized.strip_prefix("---\n") {
        serialized = stripped.to_string();
    }
    Ok(serialized.trim().to_string())
}

fn spaces(indent: usize) -> String {
    " ".repeat(indent)
}

#[cfg(test)]
mod tests {
    use super::{generate_anchored_compose, AnchorMode};
    use crate::heuristics::DeployMode;

    #[test]
    fn generate_anchored_compose_auto_emits_core_anchor_for_shared_services() {
        let input = r#"
services:
  api:
    image: nginx:1.27
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
  worker:
    image: nginx:1.27
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
"#;
        let rendered =
            generate_anchored_compose(input, DeployMode::Compose, AnchorMode::Auto, None)
                .expect("generation should succeed");
        assert!(rendered.contains("x-hardening-core: &hardening_core"));
        assert!(rendered.contains("<<: *hardening_core"));
    }

    #[test]
    fn generate_anchored_compose_minimal_keeps_non_core_defaults_inlined() {
        let input = r#"
services:
  api:
    image: nginx:1.27
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    cpus: "1.0"
    mem_limit: 512m
    pids_limit: 256
  worker:
    image: nginx:1.27
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    cpus: "1.0"
    mem_limit: 512m
    pids_limit: 256
"#;
        let rendered =
            generate_anchored_compose(input, DeployMode::Compose, AnchorMode::Minimal, None)
                .expect("generation should succeed");
        assert!(rendered.contains("x-hardening-core: &hardening_core"));
        assert!(!rendered.contains("x-resource-defaults-compose: &resource_defaults_compose"));
        assert!(rendered.contains("cpus:"));
        assert!(!rendered.contains("x-composite-"));
    }

    #[test]
    fn generate_anchored_compose_full_emits_resource_anchor() {
        let input = r#"
services:
  api:
    image: nginx:1.27
    cpus: "1.0"
    mem_limit: 512m
    pids_limit: 256
  worker:
    image: nginx:1.27
    cpus: "1.0"
    mem_limit: 512m
    pids_limit: 256
"#;
        let rendered =
            generate_anchored_compose(input, DeployMode::Compose, AnchorMode::Full, None)
                .expect("generation should succeed");
        assert!(rendered.contains("x-resource-defaults-compose: &resource_defaults_compose"));
        assert!(rendered.contains("<<: *resource_defaults_compose"));
    }

    #[test]
    fn generate_anchored_compose_merges_multiple_anchors_with_single_merge_key() {
        let input = r#"
services:
  api:
    image: nginx:1.27
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    cpus: "1.0"
    mem_limit: 512m
    pids_limit: 256
  worker:
    image: nginx:1.27
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    cpus: "1.0"
    mem_limit: 512m
    pids_limit: 256
"#;
        let rendered =
            generate_anchored_compose(input, DeployMode::Compose, AnchorMode::Full, None)
                .expect("generation should succeed");
        assert!(rendered.contains("<<: [*hardening_core, *resource_defaults_compose]"));
    }

    #[test]
    fn generate_anchored_compose_auto_emits_composite_anchor_for_intersection() {
        let input = r#"
services:
  api:
    image: nginx:1.27
    logging:
      driver: json-file
      options:
        max-size: "10m"
    stop_grace_period: 30s
  worker:
    image: redis:7
    logging:
      driver: json-file
      options:
        max-size: "10m"
    stop_grace_period: 30s
"#;
        let rendered =
            generate_anchored_compose(input, DeployMode::Compose, AnchorMode::Auto, None)
                .expect("generation should succeed");
        assert!(rendered.contains("x-composite-"));
        assert!(rendered.contains("<<: *composite_"));
    }

    #[test]
    fn generate_anchored_compose_orders_defaults_before_composites() {
        let input = r#"
services:
  api:
    image: nginx:1.27
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    logging:
      driver: json-file
      options:
        max-size: "10m"
    stop_grace_period: 30s
  worker:
    image: redis:7
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    logging:
      driver: json-file
      options:
        max-size: "10m"
    stop_grace_period: 30s
"#;
        let rendered =
            generate_anchored_compose(input, DeployMode::Compose, AnchorMode::Auto, None)
                .expect("generation should succeed");
        assert!(rendered.contains("<<: [*hardening_core, *composite_"));
    }
}
