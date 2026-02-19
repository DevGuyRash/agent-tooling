//! Deterministic anchor suggestion engine for hardened compose documents.

use std::collections::{BTreeMap, BTreeSet};

use serde::Serialize;
use serde_yaml::{Mapping, Value as YamlValue};

use crate::error::AppError;
use crate::heuristics::DeployMode;

const MAX_COMPOSITE_ATOMS: usize = 48;
const MAX_COMPOSITE_KEYS: usize = 6;
const MAX_COMPOSITE_RAW_CANDIDATES: usize = 10_000;

/// Options controlling anchor suggestion behavior.
#[derive(Debug, Clone)]
pub struct SuggestionOptions {
    /// Deployment mode used by surrounding compose policy evaluation.
    pub mode: DeployMode,
    /// Optional override for minimum service usage count.
    pub min_usage_override: Option<usize>,
    /// Include sensitive/noisy path suggestions (`environment`, `command`, etc).
    pub include_sensitive: bool,
    /// Maximum number of suggestions to emit.
    pub max_suggestions: usize,
}

/// Machine-readable anchor suggestion report.
#[derive(Debug, Clone, Serialize)]
pub struct AnchorSuggestionReport {
    /// Report schema version.
    pub schema_version: u32,
    /// Deployment mode used while generating this report.
    pub mode: String,
    /// Number of services analyzed.
    pub service_count: usize,
    /// Effective minimum usage threshold.
    pub threshold_used: usize,
    /// Deterministically sorted suggestions.
    pub suggestions: Vec<AnchorSuggestion>,
}

/// One proposed anchor fragment.
#[derive(Debug, Clone, Serialize)]
pub struct AnchorSuggestion {
    /// Stable suggestion identifier (`SUG-1`, `SUG-2`, ...).
    pub id: String,
    /// Exact-fragment or composite/intersection suggestion kind.
    pub kind: SuggestionKind,
    /// Suggested logical anchor name.
    pub proposed_name: String,
    /// Suggested YAML key (`x-*`).
    pub proposed_yaml_key: String,
    /// Wildcarded compose path signature (`services.*.foo.bar`).
    pub path_signature: String,
    /// Number of services sharing this fragment.
    pub usage_count: usize,
    /// Number of top-level keys represented by the fragment.
    pub key_count: usize,
    /// Sorted service names where the fragment appears.
    pub service_names: Vec<String>,
    /// Suggested reusable fragment.
    pub fragment: YamlValue,
    /// Deterministic confidence score (0.0-1.0).
    pub confidence: f32,
    /// Risk label for review ordering.
    pub risk: SuggestionRisk,
    /// Deterministic strategy descriptor.
    pub strategy: String,
    /// Deterministic rationale tags.
    pub reasons: Vec<String>,
}

/// Suggestion kind.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum SuggestionKind {
    /// Exact repeated fragment at a specific path.
    Exact,
    /// Intersection/composite discovered across service mappings.
    Composite,
}

/// Risk label for a suggestion.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum SuggestionRisk {
    /// Low review risk.
    Low,
    /// Medium review risk.
    Medium,
    /// High review risk.
    High,
}

#[derive(Debug, Clone)]
struct SignatureBucket {
    path_signature: String,
    fragment: YamlValue,
    normalized_fragment: String,
    services: BTreeSet<String>,
}

#[derive(Debug, Clone)]
struct PreparedSuggestion {
    kind: SuggestionKind,
    path_signature: String,
    usage_count: usize,
    key_count: usize,
    service_names: Vec<String>,
    fragment: YamlValue,
    normalized_fragment: String,
    confidence: f32,
    risk: SuggestionRisk,
    strategy: String,
    reasons: Vec<String>,
    name_hint: Option<String>,
    yaml_key_hint: Option<String>,
}

#[derive(Debug, Clone)]
struct AtomSupport {
    id: String,
    key: String,
    value: YamlValue,
    services: BTreeSet<String>,
}

#[derive(Debug, Clone)]
struct RawCompositeCandidate {
    keys: Vec<String>,
    services: BTreeSet<String>,
    fragment: YamlValue,
    normalized_fragment: String,
}

/// Reusable composite candidate consumed by compose generation.
#[derive(Debug, Clone)]
pub(crate) struct CompositeAnchorCandidate {
    pub(crate) name: String,
    pub(crate) yaml_key: String,
    pub(crate) usage_count: usize,
    pub(crate) key_count: usize,
    pub(crate) service_names: Vec<String>,
    pub(crate) body: YamlValue,
}

/// Discover deterministic composite anchors from a service mapping.
///
/// The input mapping must have service names as keys and per-service mappings as values.
pub(crate) fn discover_composite_anchors(
    services: &Mapping,
    threshold: usize,
    max_candidates: usize,
) -> Result<Vec<CompositeAnchorCandidate>, AppError> {
    if threshold < 2 || max_candidates == 0 {
        return Ok(Vec::new());
    }

    let mut raw = discover_raw_composites(services, threshold)?;
    if raw.is_empty() {
        return Ok(Vec::new());
    }

    raw.sort_by(|left, right| {
        (
            std::cmp::Reverse(left.keys.len()),
            std::cmp::Reverse(left.services.len()),
            left.normalized_fragment.as_str(),
        )
            .cmp(&(
                std::cmp::Reverse(right.keys.len()),
                std::cmp::Reverse(right.services.len()),
                right.normalized_fragment.as_str(),
            ))
    });
    if raw.len() > max_candidates {
        raw.truncate(max_candidates);
    }

    let mut used_yaml_keys: BTreeMap<String, usize> = BTreeMap::new();
    let mut output = Vec::new();
    for candidate in raw {
        let service_names: Vec<String> = candidate.services.iter().cloned().collect();
        let (name, yaml_key) = composite_name_and_key(
            candidate
                .keys
                .first()
                .map(String::as_str)
                .unwrap_or("fragment"),
            &candidate.normalized_fragment,
            &service_names,
            &mut used_yaml_keys,
        );

        output.push(CompositeAnchorCandidate {
            name,
            yaml_key,
            usage_count: candidate.services.len(),
            key_count: candidate.keys.len(),
            service_names,
            body: candidate.fragment,
        });
    }

    Ok(output)
}

/// Generate deterministic anchor suggestions from a hardened compose document.
///
/// # Arguments
/// * `hardened_yaml` - Hardened compose yaml content.
/// * `opts` - Suggestion engine options.
///
/// # Returns
/// * `Ok(AnchorSuggestionReport)` when suggestion generation succeeds.
/// * `Err(AppError)` on parse or analysis failure.
pub fn suggest_anchors(
    hardened_yaml: &str,
    opts: &SuggestionOptions,
) -> Result<AnchorSuggestionReport, AppError> {
    let root: YamlValue =
        serde_yaml::from_str(hardened_yaml).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse hardened compose yaml: {error}"),
        })?;
    let services = root
        .as_mapping()
        .and_then(|mapping| mapping.get(YamlValue::String("services".to_string())))
        .and_then(YamlValue::as_mapping)
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose input must include a services mapping".to_string(),
        })?;

    let mut service_names: Vec<String> = services
        .keys()
        .filter_map(YamlValue::as_str)
        .map(ToOwned::to_owned)
        .collect();
    service_names.sort();
    let service_count = service_names.len();
    let threshold = opts
        .min_usage_override
        .unwrap_or_else(|| adaptive_threshold(service_count));

    let mut prepared = collect_exact_suggestions(services, &service_names, threshold, opts)?;

    let composite = discover_composite_anchors(services, threshold, opts.max_suggestions)?;
    for candidate in composite {
        let composite_keys = top_level_fragment_keys(&candidate.body).join(",");
        let sensitive = candidate.body.as_mapping().is_some_and(|map| {
            map.keys()
                .filter_map(YamlValue::as_str)
                .any(is_sensitive_key)
        });
        let hardening_or_resource = candidate.body.as_mapping().is_some_and(|map| {
            map.keys()
                .filter_map(YamlValue::as_str)
                .any(is_hardening_or_resource_key)
        });
        let risk = classify_risk(sensitive, hardening_or_resource);
        let confidence = compute_composite_confidence(
            candidate.usage_count,
            threshold,
            candidate.key_count,
            sensitive,
            hardening_or_resource,
        );
        let normalized_fragment =
            serde_yaml::to_string(&candidate.body).map_err(|error| AppError::InvalidInput {
                reason: format!("failed to serialize composite fragment: {error}"),
            })?;

        prepared.push(PreparedSuggestion {
            kind: SuggestionKind::Composite,
            path_signature: "services.*.{composite}".to_string(),
            usage_count: candidate.usage_count,
            key_count: candidate.key_count,
            service_names: candidate.service_names,
            fragment: candidate.body,
            normalized_fragment,
            confidence,
            risk,
            strategy: "intersection-frequent-itemset".to_string(),
            reasons: vec![
                "composite-intersection".to_string(),
                format!("usage-at-least-threshold:{threshold}"),
                format!("composite-keys:{composite_keys}"),
            ],
            name_hint: Some(candidate.name),
            yaml_key_hint: Some(candidate.yaml_key),
        });
    }

    prepared.sort_by(|left, right| {
        (
            risk_rank(left.risk),
            confidence_key(right.confidence),
            std::cmp::Reverse(left.key_count),
            std::cmp::Reverse(left.usage_count),
            kind_rank(left.kind),
            left.path_signature.as_str(),
            left.normalized_fragment.as_str(),
        )
            .cmp(&(
                risk_rank(right.risk),
                confidence_key(left.confidence),
                std::cmp::Reverse(right.key_count),
                std::cmp::Reverse(right.usage_count),
                kind_rank(right.kind),
                right.path_signature.as_str(),
                right.normalized_fragment.as_str(),
            ))
    });

    if prepared.len() > opts.max_suggestions {
        prepared.truncate(opts.max_suggestions);
    }

    let mut used_keys: BTreeMap<String, usize> = BTreeMap::new();
    let mut suggestions = Vec::new();
    for (index, item) in prepared.into_iter().enumerate() {
        let (mut proposed_name, key_root) = match item.kind {
            SuggestionKind::Composite => {
                let name = item
                    .name_hint
                    .unwrap_or_else(|| "composite_fragment".to_string());
                let key = item
                    .yaml_key_hint
                    .unwrap_or_else(|| "x-composite-fragment".to_string());
                (name, key)
            }
            SuggestionKind::Exact => {
                let category = categorize_path(&item.path_signature, item.risk);
                let base = sanitize_name(&last_path_segment(&item.path_signature));
                let name = format!("{category}_{base}");
                (name.clone(), format!("x-{}", name.replace('_', "-")))
            }
        };

        let counter = used_keys.entry(key_root.clone()).or_insert(0);
        *counter += 1;
        let proposed_yaml_key = if *counter == 1 {
            key_root
        } else {
            proposed_name = format!("{proposed_name}_{}", *counter);
            format!("x-{}", proposed_name.replace('_', "-"))
        };

        suggestions.push(AnchorSuggestion {
            id: format!("SUG-{}", index + 1),
            kind: item.kind,
            proposed_name,
            proposed_yaml_key,
            path_signature: item.path_signature,
            usage_count: item.usage_count,
            key_count: item.key_count,
            service_names: item.service_names,
            fragment: item.fragment,
            confidence: item.confidence,
            risk: item.risk,
            strategy: item.strategy,
            reasons: item.reasons,
        });
    }

    Ok(AnchorSuggestionReport {
        schema_version: 2,
        mode: match opts.mode {
            DeployMode::Compose => "compose".to_string(),
            DeployMode::Swarm => "swarm".to_string(),
        },
        service_count,
        threshold_used: threshold,
        suggestions,
    })
}

fn collect_exact_suggestions(
    services: &Mapping,
    service_names: &[String],
    threshold: usize,
    opts: &SuggestionOptions,
) -> Result<Vec<PreparedSuggestion>, AppError> {
    let mut buckets: BTreeMap<String, SignatureBucket> = BTreeMap::new();
    for service_name in service_names {
        let service = services
            .get(YamlValue::String(service_name.clone()))
            .and_then(YamlValue::as_mapping)
            .ok_or_else(|| AppError::InvalidInput {
                reason: format!("service {service_name} must be a mapping"),
            })?;
        collect_signatures(
            service_name,
            "services.*",
            &YamlValue::Mapping(service.clone()),
            &mut buckets,
        )?;
    }

    let mut prepared = Vec::new();
    for bucket in buckets.values() {
        let usage_count = bucket.services.len();
        if usage_count < threshold {
            continue;
        }

        let sensitive = is_sensitive_path(&bucket.path_signature);
        if sensitive && !opts.include_sensitive {
            continue;
        }

        let hardening_or_resource = is_hardening_or_resource_path(&bucket.path_signature);
        let risk = classify_risk(sensitive, hardening_or_resource);
        let confidence = compute_confidence(
            usage_count,
            threshold,
            path_depth(&bucket.path_signature),
            sensitive,
            hardening_or_resource,
        );
        let mut reasons = Vec::new();
        reasons.push("repeated-across-services".to_string());
        reasons.push(format!("usage-at-least-threshold:{threshold}"));
        if sensitive {
            reasons.push("sensitive-key-pattern".to_string());
        }
        if hardening_or_resource {
            reasons.push("hardening-or-resource-pattern".to_string());
        }

        prepared.push(PreparedSuggestion {
            kind: SuggestionKind::Exact,
            path_signature: bucket.path_signature.clone(),
            usage_count,
            key_count: key_count_for_fragment(&bucket.fragment),
            service_names: bucket.services.iter().cloned().collect(),
            fragment: bucket.fragment.clone(),
            normalized_fragment: bucket.normalized_fragment.clone(),
            confidence,
            risk,
            strategy: "exact-fragment".to_string(),
            reasons,
            name_hint: None,
            yaml_key_hint: None,
        });
    }

    Ok(prepared)
}

fn discover_raw_composites(
    services: &Mapping,
    threshold: usize,
) -> Result<Vec<RawCompositeCandidate>, AppError> {
    let mut atom_by_id: BTreeMap<String, AtomSupport> = BTreeMap::new();

    let mut service_names: Vec<String> = services
        .keys()
        .filter_map(YamlValue::as_str)
        .map(ToOwned::to_owned)
        .collect();
    service_names.sort();

    for service_name in &service_names {
        let service = services
            .get(YamlValue::String(service_name.clone()))
            .and_then(YamlValue::as_mapping)
            .ok_or_else(|| AppError::InvalidInput {
                reason: format!("service {service_name} must be a mapping"),
            })?;

        for (key, value) in service {
            let Some(key_name) = key.as_str() else {
                continue;
            };
            if key_name == "<<" {
                continue;
            }

            let canonical = canonicalize_value(value);
            let normalized =
                serde_yaml::to_string(&canonical).map_err(|error| AppError::InvalidInput {
                    reason: format!("failed to serialize composite atom: {error}"),
                })?;
            let atom_id = format!("{key_name}::{normalized}");
            let entry = atom_by_id
                .entry(atom_id.clone())
                .or_insert_with(|| AtomSupport {
                    id: atom_id,
                    key: key_name.to_string(),
                    value: canonical.clone(),
                    services: BTreeSet::new(),
                });
            entry.services.insert(service_name.clone());
        }
    }

    let mut frequent_atoms: Vec<AtomSupport> = atom_by_id
        .into_values()
        .filter(|atom| atom.services.len() >= threshold)
        .collect();
    if frequent_atoms.len() < 2 {
        return Ok(Vec::new());
    }

    frequent_atoms.sort_by(|left, right| {
        (std::cmp::Reverse(left.services.len()), left.id.as_str())
            .cmp(&(std::cmp::Reverse(right.services.len()), right.id.as_str()))
    });
    if frequent_atoms.len() > MAX_COMPOSITE_ATOMS {
        frequent_atoms.truncate(MAX_COMPOSITE_ATOMS);
    }
    frequent_atoms.sort_by(|left, right| left.id.cmp(&right.id));

    let mut raw = Vec::new();
    let mut atom_indexes = Vec::new();
    let mut seen = BTreeSet::new();
    enumerate_composites(
        &frequent_atoms,
        threshold,
        &mut atom_indexes,
        &mut raw,
        &mut seen,
        None,
        0,
    )?;

    prune_dominated_composites(raw)
}

fn enumerate_composites(
    atoms: &[AtomSupport],
    threshold: usize,
    current_indexes: &mut Vec<usize>,
    output: &mut Vec<RawCompositeCandidate>,
    seen: &mut BTreeSet<String>,
    current_services: Option<BTreeSet<String>>,
    start_index: usize,
) -> Result<(), AppError> {
    if output.len() >= MAX_COMPOSITE_RAW_CANDIDATES {
        return Ok(());
    }

    for index in start_index..atoms.len() {
        let services = if let Some(existing) = &current_services {
            existing
                .intersection(&atoms[index].services)
                .cloned()
                .collect::<BTreeSet<String>>()
        } else {
            atoms[index].services.clone()
        };

        if services.len() < threshold {
            continue;
        }

        current_indexes.push(index);

        if current_indexes.len() >= 2 {
            let mut keys = BTreeSet::new();
            for atom_index in current_indexes.iter().copied() {
                keys.insert(atoms[atom_index].key.clone());
            }

            if keys.len() == current_indexes.len() {
                let fragment = mapping_from_atoms(atoms, current_indexes);
                let normalized_fragment =
                    serde_yaml::to_string(&fragment).map_err(|error| AppError::InvalidInput {
                        reason: format!("failed to serialize composite fragment: {error}"),
                    })?;

                let fingerprint = format!(
                    "{}::{}",
                    normalized_fragment,
                    services.iter().cloned().collect::<Vec<String>>().join(",")
                );
                if seen.insert(fingerprint) {
                    output.push(RawCompositeCandidate {
                        keys: keys.into_iter().collect(),
                        services: services.clone(),
                        fragment,
                        normalized_fragment,
                    });
                    if output.len() >= MAX_COMPOSITE_RAW_CANDIDATES {
                        let _ = current_indexes.pop();
                        return Ok(());
                    }
                }
            }
        }

        if current_indexes.len() < MAX_COMPOSITE_KEYS {
            enumerate_composites(
                atoms,
                threshold,
                current_indexes,
                output,
                seen,
                Some(services),
                index + 1,
            )?;
        }

        let _ = current_indexes.pop();
    }

    Ok(())
}

fn mapping_from_atoms(atoms: &[AtomSupport], indexes: &[usize]) -> YamlValue {
    let mut entries: Vec<(String, YamlValue)> = indexes
        .iter()
        .copied()
        .map(|index| (atoms[index].key.clone(), atoms[index].value.clone()))
        .collect();
    entries.sort_by(|left, right| left.0.cmp(&right.0));

    let mut mapping = Mapping::new();
    for (key, value) in entries {
        mapping.insert(YamlValue::String(key), value);
    }
    YamlValue::Mapping(mapping)
}

fn prune_dominated_composites(
    mut candidates: Vec<RawCompositeCandidate>,
) -> Result<Vec<RawCompositeCandidate>, AppError> {
    candidates.sort_by(|left, right| {
        (
            std::cmp::Reverse(left.keys.len()),
            std::cmp::Reverse(left.services.len()),
            left.normalized_fragment.as_str(),
        )
            .cmp(&(
                std::cmp::Reverse(right.keys.len()),
                std::cmp::Reverse(right.services.len()),
                right.normalized_fragment.as_str(),
            ))
    });

    let mut retained: Vec<RawCompositeCandidate> = Vec::new();
    for candidate in candidates {
        let candidate_key_set: BTreeSet<&str> = candidate.keys.iter().map(String::as_str).collect();
        let dominated = retained.iter().any(|existing| {
            if existing.services != candidate.services
                || existing.keys.len() <= candidate.keys.len()
            {
                return false;
            }
            let existing_keys: BTreeSet<&str> = existing.keys.iter().map(String::as_str).collect();
            candidate_key_set.is_subset(&existing_keys)
        });
        if dominated {
            continue;
        }
        retained.push(candidate);
    }

    retained.sort_by(|left, right| {
        (
            left.keys.join(","),
            left.normalized_fragment.as_str(),
            left.services
                .iter()
                .cloned()
                .collect::<Vec<String>>()
                .join(","),
        )
            .cmp(&(
                right.keys.join(","),
                right.normalized_fragment.as_str(),
                right
                    .services
                    .iter()
                    .cloned()
                    .collect::<Vec<String>>()
                    .join(","),
            ))
    });

    Ok(retained)
}

/// Render an anchor suggestion report in deterministic markdown format.
pub fn render_markdown_report(report: &AnchorSuggestionReport) -> Result<String, AppError> {
    let mut out = String::new();
    out.push_str("# Anchor Suggestions\n\n");
    out.push_str(&format!(
        "- schema_version: {}\n- mode: {}\n- service_count: {}\n- threshold_used: {}\n- suggestions: {}\n\n",
        report.schema_version,
        report.mode,
        report.service_count,
        report.threshold_used,
        report.suggestions.len()
    ));

    for suggestion in &report.suggestions {
        out.push_str(&format!("## {}\n", suggestion.id));
        out.push_str(&format!(
            "- kind: `{}`\n",
            suggestion_kind_label(suggestion.kind)
        ));
        out.push_str(&format!("- key: `{}`\n", suggestion.proposed_yaml_key));
        out.push_str(&format!("- path: `{}`\n", suggestion.path_signature));
        out.push_str(&format!("- usage: {}\n", suggestion.usage_count));
        out.push_str(&format!("- key_count: {}\n", suggestion.key_count));
        out.push_str(&format!("- risk: `{}`\n", risk_label(suggestion.risk)));
        out.push_str(&format!("- strategy: `{}`\n", suggestion.strategy));
        out.push_str(&format!("- confidence: {:.2}\n", suggestion.confidence));
        out.push_str("- services:\n");
        for service in &suggestion.service_names {
            out.push_str(&format!("  - `{service}`\n"));
        }
        out.push_str("- reasons:\n");
        for reason in &suggestion.reasons {
            out.push_str(&format!("  - `{reason}`\n"));
        }
        out.push_str("\n```yaml\n");
        match &suggestion.fragment {
            YamlValue::Mapping(_) | YamlValue::Sequence(_) => {
                out.push_str(&format!("{}:\n", suggestion.proposed_yaml_key));
                let fragment = serde_yaml::to_string(&suggestion.fragment).map_err(|error| {
                    AppError::InvalidInput {
                        reason: format!("failed to render suggestion fragment as yaml: {error}"),
                    }
                })?;
                for line in fragment.lines() {
                    if line == "---" {
                        continue;
                    }
                    out.push_str("  ");
                    out.push_str(line);
                    out.push('\n');
                }
            }
            _ => {
                let scalar = serde_yaml::to_string(&suggestion.fragment).map_err(|error| {
                    AppError::InvalidInput {
                        reason: format!(
                            "failed to render scalar suggestion fragment as yaml: {error}"
                        ),
                    }
                })?;
                let value = scalar
                    .lines()
                    .filter(|line| *line != "---")
                    .collect::<Vec<&str>>()
                    .join(" ");
                out.push_str(&format!(
                    "{}: {}\n",
                    suggestion.proposed_yaml_key,
                    value.trim()
                ));
            }
        }
        out.push_str("```\n\n");
    }

    Ok(out)
}

fn adaptive_threshold(service_count: usize) -> usize {
    if service_count > 5 {
        3
    } else {
        2
    }
}

fn collect_signatures(
    service_name: &str,
    path: &str,
    value: &YamlValue,
    buckets: &mut BTreeMap<String, SignatureBucket>,
) -> Result<(), AppError> {
    match value {
        YamlValue::Mapping(map) => {
            if !map.is_empty() && path != "services.*" {
                insert_bucket(service_name, path, value, buckets)?;
            }

            let mut keys: Vec<String> = map
                .keys()
                .filter_map(YamlValue::as_str)
                .map(ToOwned::to_owned)
                .collect();
            keys.sort();
            for key in keys {
                let child = map.get(YamlValue::String(key.clone())).ok_or_else(|| {
                    AppError::InvalidInput {
                        reason: format!("missing key while traversing compose tree: {key}"),
                    }
                })?;
                let child_path = format!("{path}.{key}");
                collect_signatures(service_name, &child_path, child, buckets)?;
            }
        }
        YamlValue::Sequence(items) => {
            if !items.is_empty() {
                insert_bucket(service_name, path, value, buckets)?;
            }
            // O(n) where n = sequence length (expected: small).
            for item in items {
                if matches!(item, YamlValue::Mapping(_) | YamlValue::Sequence(_)) {
                    let child_path = format!("{path}.[]");
                    collect_signatures(service_name, &child_path, item, buckets)?;
                }
            }
        }
        _ => {
            if path != "services.*" {
                insert_bucket(service_name, path, value, buckets)?;
            }
        }
    }
    Ok(())
}

fn insert_bucket(
    service_name: &str,
    path: &str,
    value: &YamlValue,
    buckets: &mut BTreeMap<String, SignatureBucket>,
) -> Result<(), AppError> {
    let canonical = canonicalize_value(value);
    let normalized_fragment =
        serde_yaml::to_string(&canonical).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to serialize canonical fragment: {error}"),
        })?;
    let key = format!("{path}::{normalized_fragment}");
    let bucket = buckets.entry(key).or_insert_with(|| SignatureBucket {
        path_signature: path.to_string(),
        fragment: canonical.clone(),
        normalized_fragment: normalized_fragment.clone(),
        services: BTreeSet::new(),
    });
    bucket.services.insert(service_name.to_string());
    Ok(())
}

fn canonicalize_value(value: &YamlValue) -> YamlValue {
    match value {
        YamlValue::Mapping(map) => {
            let mut entries: Vec<(String, YamlValue)> = map
                .iter()
                .filter_map(|(key, item)| key.as_str().map(|text| (text.to_string(), item)))
                .map(|(key, item)| (key, canonicalize_value(item)))
                .collect();
            entries.sort_by(|left, right| left.0.cmp(&right.0));
            let mut rendered = Mapping::new();
            for (key, item) in entries {
                rendered.insert(YamlValue::String(key), item);
            }
            YamlValue::Mapping(rendered)
        }
        YamlValue::Sequence(items) => {
            YamlValue::Sequence(items.iter().map(canonicalize_value).collect())
        }
        _ => value.clone(),
    }
}

fn is_sensitive_path(path: &str) -> bool {
    let sensitive_segments = ["environment", "labels", "command", "entrypoint"];
    sensitive_segments
        .iter()
        .any(|segment| path.split('.').any(|item| item == *segment))
}

fn is_hardening_or_resource_path(path: &str) -> bool {
    let hardened = [
        "read_only",
        "security_opt",
        "cap_drop",
        "cap_add",
        "cpus",
        "mem_limit",
        "pids_limit",
        "deploy",
        "resources",
        "healthcheck",
        "tmpfs",
    ];
    hardened
        .iter()
        .any(|segment| path.split('.').any(|item| item == *segment))
}

fn is_sensitive_key(key: &str) -> bool {
    matches!(key, "environment" | "labels" | "command" | "entrypoint")
}

fn is_hardening_or_resource_key(key: &str) -> bool {
    matches!(
        key,
        "read_only"
            | "security_opt"
            | "cap_drop"
            | "cap_add"
            | "cpus"
            | "mem_limit"
            | "pids_limit"
            | "deploy"
            | "resources"
            | "healthcheck"
            | "tmpfs"
    )
}

fn classify_risk(sensitive: bool, hardening_or_resource: bool) -> SuggestionRisk {
    if sensitive {
        return SuggestionRisk::High;
    }
    if hardening_or_resource {
        return SuggestionRisk::Low;
    }
    SuggestionRisk::Medium
}

fn compute_confidence(
    usage_count: usize,
    threshold: usize,
    depth: usize,
    sensitive: bool,
    hardening_or_resource: bool,
) -> f32 {
    let mut score = 0.5_f32;
    if usage_count >= threshold {
        score += 0.1;
    }
    if usage_count > threshold {
        score += 0.1;
    }
    if depth > 1 {
        score += 0.1;
    }
    if hardening_or_resource {
        score += 0.1;
    }
    if sensitive {
        score -= 0.2;
    }
    score.clamp(0.0, 1.0)
}

fn compute_composite_confidence(
    usage_count: usize,
    threshold: usize,
    key_count: usize,
    sensitive: bool,
    hardening_or_resource: bool,
) -> f32 {
    let mut score = 0.55_f32;
    if usage_count >= threshold {
        score += 0.1;
    }
    if usage_count > threshold {
        score += 0.1;
    }
    if key_count >= 3 {
        score += 0.1;
    }
    if hardening_or_resource {
        score += 0.1;
    }
    if sensitive {
        score -= 0.15;
    }
    score.clamp(0.0, 1.0)
}

fn path_depth(path: &str) -> usize {
    path.split('.').count()
}

fn risk_rank(risk: SuggestionRisk) -> u8 {
    match risk {
        SuggestionRisk::Low => 0,
        SuggestionRisk::Medium => 1,
        SuggestionRisk::High => 2,
    }
}

fn kind_rank(kind: SuggestionKind) -> u8 {
    match kind {
        SuggestionKind::Composite => 0,
        SuggestionKind::Exact => 1,
    }
}

fn confidence_key(value: f32) -> i32 {
    // Keep deterministic sort for floats without exposing precision noise.
    (value * 1000.0).round() as i32
}

fn last_path_segment(path: &str) -> String {
    path.split('.')
        .rfind(|segment| *segment != "[]" && !segment.is_empty())
        .unwrap_or("fragment")
        .to_string()
}

fn key_count_for_fragment(fragment: &YamlValue) -> usize {
    fragment.as_mapping().map(Mapping::len).unwrap_or(1).max(1)
}

fn top_level_fragment_keys(fragment: &YamlValue) -> Vec<String> {
    let mut keys: Vec<String> = fragment
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

fn categorize_path(path: &str, risk: SuggestionRisk) -> &'static str {
    if is_hardening_or_resource_path(path) {
        if path.contains("resources") || path.contains("cpus") || path.contains("mem_limit") {
            return "resource";
        }
        return "hardening";
    }
    if risk == SuggestionRisk::High {
        return "app";
    }
    "runtime"
}

fn sanitize_name(value: &str) -> String {
    let lower = value.to_ascii_lowercase();
    let mut output = String::new();
    let mut prev_underscore = false;
    for ch in lower.chars() {
        if ch.is_ascii_alphanumeric() {
            output.push(ch);
            prev_underscore = false;
            continue;
        }
        if !prev_underscore {
            output.push('_');
            prev_underscore = true;
        }
    }
    let trimmed = output.trim_matches('_').to_string();
    if trimmed.is_empty() {
        return "fragment".to_string();
    }
    trimmed
}

fn stable_hash_hex8(value: &str) -> String {
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in value.as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{:08x}", hash as u32)
}

fn composite_name_and_key(
    primary_key: &str,
    normalized_fragment: &str,
    service_names: &[String],
    used_yaml_keys: &mut BTreeMap<String, usize>,
) -> (String, String) {
    let base = sanitize_name(primary_key);
    let fingerprint = format!("{}|{}", normalized_fragment, service_names.join(","));
    let hash = stable_hash_hex8(&fingerprint);
    let mut proposed_name = format!("composite_{base}_{hash}");
    let key_root = format!("x-composite-{base}-{hash}");

    let counter = used_yaml_keys.entry(key_root.clone()).or_insert(0);
    *counter += 1;
    let yaml_key = if *counter == 1 {
        key_root
    } else {
        proposed_name = format!("{proposed_name}_{}", *counter);
        format!("x-{}", proposed_name.replace('_', "-"))
    };

    (proposed_name, yaml_key)
}

fn suggestion_kind_label(kind: SuggestionKind) -> &'static str {
    match kind {
        SuggestionKind::Exact => "exact",
        SuggestionKind::Composite => "composite",
    }
}

fn risk_label(risk: SuggestionRisk) -> &'static str {
    match risk {
        SuggestionRisk::Low => "low",
        SuggestionRisk::Medium => "medium",
        SuggestionRisk::High => "high",
    }
}

#[cfg(test)]
mod tests {
    use super::{
        discover_composite_anchors, render_markdown_report, suggest_anchors, SuggestionKind,
        SuggestionOptions, SuggestionRisk,
    };
    use crate::heuristics::DeployMode;
    use serde_yaml::{Mapping, Value as YamlValue};

    #[test]
    fn suggest_anchors_detects_repeated_hardening_block() {
        let input = r#"
services:
  api:
    read_only: true
    cap_drop:
      - ALL
  worker:
    read_only: true
    cap_drop:
      - ALL
"#;
        let report = suggest_anchors(
            input,
            &SuggestionOptions {
                mode: DeployMode::Compose,
                min_usage_override: Some(2),
                include_sensitive: true,
                max_suggestions: 50,
            },
        )
        .expect("suggestions should be generated");
        assert!(!report.suggestions.is_empty());
        assert!(report
            .suggestions
            .iter()
            .any(|item| item.path_signature == "services.*.cap_drop"));
    }

    #[test]
    fn suggest_anchors_uses_adaptive_threshold_for_larger_stacks() {
        let input = r#"
services:
  s1: { read_only: true }
  s2: { read_only: true }
  s3: { read_only: true }
  s4: { read_only: true }
  s5: { read_only: true }
  s6: { read_only: true }
"#;
        let report = suggest_anchors(
            input,
            &SuggestionOptions {
                mode: DeployMode::Compose,
                min_usage_override: None,
                include_sensitive: true,
                max_suggestions: 50,
            },
        )
        .expect("suggestions should be generated");
        assert_eq!(report.threshold_used, 3);
    }

    #[test]
    fn suggest_anchors_marks_sensitive_paths_high_risk() {
        let input = r#"
services:
  api:
    environment:
      A: "1"
  worker:
    environment:
      A: "1"
"#;
        let report = suggest_anchors(
            input,
            &SuggestionOptions {
                mode: DeployMode::Compose,
                min_usage_override: Some(2),
                include_sensitive: true,
                max_suggestions: 50,
            },
        )
        .expect("suggestions should be generated");
        assert!(report
            .suggestions
            .iter()
            .any(|item| item.path_signature == "services.*.environment"
                && item.risk == SuggestionRisk::High));
    }

    #[test]
    fn suggest_anchors_discovers_composite_intersection() {
        let input = r#"
services:
  api:
    read_only: true
    security_opt: [no-new-privileges:true]
    image: nginx:1.27
  worker:
    read_only: true
    security_opt: [no-new-privileges:true]
    image: redis:7
  cron:
    read_only: true
    security_opt: [no-new-privileges:true]
    image: busybox:1.36
"#;
        let report = suggest_anchors(
            input,
            &SuggestionOptions {
                mode: DeployMode::Compose,
                min_usage_override: Some(2),
                include_sensitive: true,
                max_suggestions: 50,
            },
        )
        .expect("suggestions should be generated");

        assert!(report
            .suggestions
            .iter()
            .any(|item| item.kind == SuggestionKind::Composite
                && item.path_signature == "services.*.{composite}"
                && item.key_count >= 2));
    }

    #[test]
    fn suggest_anchors_schema_version_is_v2() {
        let input = r#"
services:
  api: { read_only: true }
  worker: { read_only: true }
"#;
        let report = suggest_anchors(
            input,
            &SuggestionOptions {
                mode: DeployMode::Compose,
                min_usage_override: Some(2),
                include_sensitive: true,
                max_suggestions: 50,
            },
        )
        .expect("suggestions should be generated");
        assert_eq!(report.schema_version, 2);
    }

    #[test]
    fn suggest_anchors_is_deterministic() {
        let input = r#"
services:
  a:
    read_only: true
    security_opt: [no-new-privileges:true]
  b:
    read_only: true
    security_opt: [no-new-privileges:true]
"#;
        let opts = SuggestionOptions {
            mode: DeployMode::Compose,
            min_usage_override: Some(2),
            include_sensitive: true,
            max_suggestions: 50,
        };
        let left = suggest_anchors(input, &opts).expect("left report");
        let right = suggest_anchors(input, &opts).expect("right report");
        let left_json = serde_json::to_string(&left).expect("serialize left");
        let right_json = serde_json::to_string(&right).expect("serialize right");
        assert_eq!(left_json, right_json);
    }

    #[test]
    fn suggest_anchors_respects_min_usage_override() {
        let input = r#"
services:
  api:
    read_only: true
  worker:
    read_only: true
"#;
        let report = suggest_anchors(
            input,
            &SuggestionOptions {
                mode: DeployMode::Compose,
                min_usage_override: Some(3),
                include_sensitive: true,
                max_suggestions: 50,
            },
        )
        .expect("suggestions should be generated");
        assert!(report.suggestions.is_empty());
    }

    #[test]
    fn suggest_anchors_respects_max_suggestions() {
        let input = r#"
services:
  api:
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
  worker:
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
"#;
        let report = suggest_anchors(
            input,
            &SuggestionOptions {
                mode: DeployMode::Compose,
                min_usage_override: Some(2),
                include_sensitive: true,
                max_suggestions: 1,
            },
        )
        .expect("suggestions should be generated");
        assert_eq!(report.suggestions.len(), 1);
    }

    #[test]
    fn render_markdown_report_includes_yaml_fragment() {
        let input = r#"
services:
  api:
    read_only: true
  worker:
    read_only: true
"#;
        let report = suggest_anchors(
            input,
            &SuggestionOptions {
                mode: DeployMode::Compose,
                min_usage_override: Some(2),
                include_sensitive: true,
                max_suggestions: 50,
            },
        )
        .expect("suggestions should be generated");
        let rendered = render_markdown_report(&report).expect("markdown should render");
        assert!(rendered.contains("# Anchor Suggestions"));
        assert!(rendered.contains("```yaml"));
        assert!(rendered.contains("- kind:"));
    }

    #[test]
    fn discover_composite_anchors_prunes_subset_when_superset_matches_same_services() {
        let mut services = Mapping::new();
        services.insert(
            YamlValue::String("api".to_string()),
            serde_yaml::from_str::<YamlValue>(
                "read_only: true\nsecurity_opt: [no-new-privileges:true]\ncap_drop: [ALL]",
            )
            .expect("yaml")
            .as_mapping()
            .cloned()
            .map(YamlValue::Mapping)
            .expect("mapping"),
        );
        services.insert(
            YamlValue::String("worker".to_string()),
            serde_yaml::from_str::<YamlValue>(
                "read_only: true\nsecurity_opt: [no-new-privileges:true]\ncap_drop: [ALL]",
            )
            .expect("yaml")
            .as_mapping()
            .cloned()
            .map(YamlValue::Mapping)
            .expect("mapping"),
        );

        let found = discover_composite_anchors(&services, 2, 100).expect("discover composites");
        assert!(!found.is_empty());
        assert!(found.iter().any(|candidate| candidate.key_count >= 3));
    }
}
