//! Deterministic policy loading and evaluation for compose and Dockerfile workflows.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use serde_yaml::{Mapping, Value as YamlValue};

use crate::dockerfile::ParsedDockerfile;
use crate::error::AppError;
use crate::fetch::normalize_image_reference;
use crate::model::CachedProfiles;

/// Supported policy domains.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PolicyDomain {
    /// Compose/Swarm service policy.
    Compose,
    /// Dockerfile/build policy.
    Dockerfile,
}

impl PolicyDomain {
    fn parse(value: &str) -> Result<Self, AppError> {
        match value {
            "compose" => Ok(Self::Compose),
            "dockerfile" => Ok(Self::Dockerfile),
            _ => Err(AppError::InvalidInput {
                reason: format!("unsupported policy domain: {value}"),
            }),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Compose => "compose",
            Self::Dockerfile => "dockerfile",
        }
    }
}

/// Supported strictness values for policy packs.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PolicyStrictness {
    /// Advisory mode.
    Advisory,
    /// Balanced mode.
    Balanced,
    /// Enforcing mode.
    Enforcing,
}

impl PolicyStrictness {
    fn parse(value: &str) -> Result<Self, AppError> {
        match value {
            "advisory" => Ok(Self::Advisory),
            "balanced" => Ok(Self::Balanced),
            "enforcing" => Ok(Self::Enforcing),
            _ => Err(AppError::InvalidInput {
                reason: format!("unsupported policy strictness: {value}"),
            }),
        }
    }
}

/// Rule severity encoded in policy packs.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RuleSeverity {
    /// Non-blocking warning.
    Warn,
    /// Blocking violation.
    Block,
}

impl RuleSeverity {
    fn parse(value: &str) -> Result<Self, AppError> {
        match value {
            "warn" => Ok(Self::Warn),
            "block" => Ok(Self::Block),
            _ => Err(AppError::InvalidInput {
                reason: format!("unsupported policy severity: {value}"),
            }),
        }
    }

    fn rank(&self) -> u8 {
        match self {
            Self::Block => 0,
            Self::Warn => 1,
        }
    }
}

/// Typed policy action.
#[derive(Debug, Clone, PartialEq)]
pub enum PolicyAction {
    /// Ensure a key equals a value.
    EnsureKey { key: String, value: YamlValue },
    /// Ensure a list contains a specific value.
    EnsureListContains { key: String, value: String },
    /// Require digest pinning for image keys.
    RequireImageDigest { key: String },
    /// Require a non-root user.
    RequireNonRootUser { key: String },
    /// Require multi-stage Dockerfile build.
    RequireMultiStage,
    /// Require OCI labels.
    RequireLabels { labels: Vec<String> },
    /// Forbid package manager usage in runtime stage.
    ForbidRuntimePackageManager,
}

/// One compiled policy rule.
#[derive(Debug, Clone, PartialEq)]
pub struct PolicyRule {
    /// Stable traceability identifier.
    pub id: String,
    /// Warning vs blocking behavior.
    pub severity: RuleSeverity,
    /// Action payload.
    pub action: PolicyAction,
    /// Target selector.
    pub target: String,
    /// Human-readable rationale.
    pub rationale: String,
}

/// Compiled policy pack.
#[derive(Debug, Clone, PartialEq)]
pub struct PolicyPack {
    /// Schema version.
    pub version: u32,
    /// Policy domain.
    pub domain: PolicyDomain,
    /// Strictness mode.
    pub strictness: PolicyStrictness,
    /// Rule list.
    pub rules: Vec<PolicyRule>,
}

/// Deterministic policy report entry.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PolicyViolation {
    /// Rule identifier.
    pub rule_id: String,
    /// Rule severity.
    pub severity: RuleSeverity,
    /// Target path.
    pub target: String,
    /// Deterministic reason.
    pub reason: String,
}

/// Deterministic patch operation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PatchOperation {
    /// Operation type:
    /// - compose: `set`, `list_add`
    /// - dockerfile: `insert_after`, `replace_instruction`
    pub op: String,
    /// Dot-path target in the evaluated document.
    pub path: String,
    /// Value to apply.
    pub value: JsonValue,
    /// Rule that produced this patch.
    pub rule_id: String,
}

/// Deterministic policy evaluation output.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PolicyEvaluation {
    /// Domain evaluated.
    pub domain: String,
    /// Strictness used.
    pub strictness: PolicyStrictness,
    /// Sorted policy violations.
    pub violations: Vec<PolicyViolation>,
    /// Sorted patch plan.
    pub patch_plan: Vec<PatchOperation>,
}

#[derive(Debug, Deserialize)]
struct RawPolicyPack {
    version: u32,
    domain: String,
    strictness: String,
    #[serde(default)]
    rules: Vec<RawPolicyRule>,
}

#[derive(Debug, Deserialize)]
struct RawPolicyRule {
    id: String,
    severity: String,
    action: String,
    target: String,
    #[serde(default)]
    key: Option<String>,
    #[serde(default)]
    value: Option<YamlValue>,
    #[serde(default)]
    labels: Vec<String>,
    #[serde(default)]
    rationale: String,
}

/// Load and compile a policy pack from disk.
///
/// # Arguments
/// * `policy_path` - YAML policy file path.
/// * `expected_domain` - Expected domain for the current workflow.
///
/// # Returns
/// * `Ok(PolicyPack)` when policy schema and actions are valid.
/// * `Err(AppError)` when the policy is missing required fields or mismatched.
pub fn load_policy_pack(
    policy_path: &Path,
    expected_domain: PolicyDomain,
) -> Result<PolicyPack, AppError> {
    let text = fs::read_to_string(policy_path)
        .map_err(|error| AppError::io(policy_path, error.to_string()))?;
    let pack = parse_policy_pack(&text)?;
    if pack.domain != expected_domain {
        return Err(AppError::InvalidInput {
            reason: format!(
                "policy domain mismatch: expected {}, got {}",
                expected_domain.as_str(),
                pack.domain.as_str()
            ),
        });
    }
    Ok(pack)
}

fn parse_policy_pack(content: &str) -> Result<PolicyPack, AppError> {
    let raw: RawPolicyPack =
        serde_yaml::from_str(content).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse policy yaml: {error}"),
        })?;

    if raw.version != 1 {
        return Err(AppError::InvalidInput {
            reason: format!("unsupported policy version: {}", raw.version),
        });
    }

    let domain = PolicyDomain::parse(&raw.domain)?;
    let strictness = PolicyStrictness::parse(&raw.strictness)?;
    if raw.rules.is_empty() {
        return Err(AppError::InvalidInput {
            reason: "policy pack must define at least one rule".to_string(),
        });
    }

    let mut rule_ids = BTreeSet::new();
    let mut rules = Vec::with_capacity(raw.rules.len());
    for raw_rule in raw.rules {
        if !rule_ids.insert(raw_rule.id.clone()) {
            return Err(AppError::InvalidInput {
                reason: format!("duplicate policy rule id: {}", raw_rule.id),
            });
        }
        rules.push(compile_rule(raw_rule)?);
    }

    Ok(PolicyPack {
        version: raw.version,
        domain,
        strictness,
        rules,
    })
}

fn compile_rule(raw: RawPolicyRule) -> Result<PolicyRule, AppError> {
    let severity = RuleSeverity::parse(&raw.severity)?;
    let action = match raw.action.as_str() {
        "ensure_key" => PolicyAction::EnsureKey {
            key: required_field(raw.key, "key", &raw.id)?,
            value: raw.value.ok_or_else(|| AppError::InvalidInput {
                reason: format!("rule {} missing required field value", raw.id),
            })?,
        },
        "ensure_list_contains" => {
            let value = raw
                .value
                .as_ref()
                .and_then(YamlValue::as_str)
                .map(ToOwned::to_owned)
                .ok_or_else(|| AppError::InvalidInput {
                    reason: format!("rule {} requires a string value", raw.id),
                })?;
            PolicyAction::EnsureListContains {
                key: required_field(raw.key, "key", &raw.id)?,
                value,
            }
        }
        "require_image_digest" => PolicyAction::RequireImageDigest {
            key: raw.key.unwrap_or_else(|| "image".to_string()),
        },
        "require_non_root_user" => PolicyAction::RequireNonRootUser {
            key: raw.key.unwrap_or_else(|| "user".to_string()),
        },
        "require_multi_stage" => PolicyAction::RequireMultiStage,
        "require_labels" => {
            if raw.labels.is_empty() {
                return Err(AppError::InvalidInput {
                    reason: format!("rule {} missing required labels", raw.id),
                });
            }
            PolicyAction::RequireLabels { labels: raw.labels }
        }
        "forbid_runtime_package_manager" => PolicyAction::ForbidRuntimePackageManager,
        _ => {
            return Err(AppError::InvalidInput {
                reason: format!("unsupported policy action: {}", raw.action),
            });
        }
    };

    Ok(PolicyRule {
        id: raw.id,
        severity,
        action,
        target: raw.target,
        rationale: raw.rationale,
    })
}

fn required_field(value: Option<String>, field: &str, rule_id: &str) -> Result<String, AppError> {
    value.ok_or_else(|| AppError::InvalidInput {
        reason: format!("rule {rule_id} missing required field {field}"),
    })
}

/// Evaluate compose input against a compose policy pack.
pub fn evaluate_compose_policy(
    compose_yaml: &str,
    cache: &CachedProfiles,
    policy: &PolicyPack,
) -> Result<PolicyEvaluation, AppError> {
    if policy.domain != PolicyDomain::Compose {
        return Err(AppError::InvalidInput {
            reason: format!(
                "evaluate_compose_policy requires compose policy, got {}",
                policy.domain.as_str()
            ),
        });
    }

    let document: YamlValue =
        serde_yaml::from_str(compose_yaml).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse compose yaml: {error}"),
        })?;
    let services = get_services_mapping(&document)?;

    let mut service_names: Vec<String> = services
        .keys()
        .filter_map(YamlValue::as_str)
        .map(ToOwned::to_owned)
        .collect();
    service_names.sort();

    let mut violations = Vec::new();
    let mut patches = Vec::new();
    for rule in &policy.rules {
        if rule.target != "service.*" {
            continue;
        }
        for service_name in &service_names {
            let service_value = services
                .get(&YamlValue::String(service_name.clone()))
                .ok_or_else(|| AppError::InvalidInput {
                    reason: format!("missing service mapping for {service_name}"),
                })?;
            let service = service_value
                .as_mapping()
                .ok_or_else(|| AppError::InvalidInput {
                    reason: format!("service {service_name} must be a mapping"),
                })?;
            evaluate_rule_for_service(
                rule,
                service_name,
                service,
                cache,
                &mut violations,
                &mut patches,
            )?;
        }
    }

    Ok(finalize_policy_output(
        policy.domain,
        &policy.strictness,
        violations,
        patches,
    ))
}

/// Evaluate Dockerfile input against a dockerfile policy pack.
pub fn evaluate_dockerfile_policy(
    dockerfile_text: &str,
    policy: &PolicyPack,
) -> Result<PolicyEvaluation, AppError> {
    if policy.domain != PolicyDomain::Dockerfile {
        return Err(AppError::InvalidInput {
            reason: format!(
                "evaluate_dockerfile_policy requires dockerfile policy, got {}",
                policy.domain.as_str()
            ),
        });
    }

    let parsed = ParsedDockerfile::parse(dockerfile_text)?;
    let mut violations = Vec::new();
    let mut patches = Vec::new();

    for rule in &policy.rules {
        match &rule.action {
            PolicyAction::RequireMultiStage => {
                if !parsed.has_multiple_stages() {
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: "dockerfile".to_string(),
                        reason: "dockerfile is not multi-stage".to_string(),
                    });
                    patches.push(PatchOperation {
                        op: "insert_after".to_string(),
                        path: "dockerfile.header".to_string(),
                        value: JsonValue::String(
                            "# AC-DF-MULTISTAGE: explicit runtime stage\nFROM scratch AS runtime"
                                .to_string(),
                        ),
                        rule_id: rule.id.clone(),
                    });
                }
            }
            PolicyAction::RequireNonRootUser { .. } => {
                let Some(_) = parsed.final_stage_range() else {
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: "dockerfile.final_stage.USER".to_string(),
                        reason: "dockerfile has no FROM stage".to_string(),
                    });
                    continue;
                };

                let current_user = parsed
                    .last_instruction_in_final_stage("USER")
                    .and_then(|instruction| parse_user_argument(&instruction.arguments));

                match current_user {
                    Some(user) if !is_root_user(&user) => {}
                    Some(_) => {
                        violations.push(PolicyViolation {
                            rule_id: rule.id.clone(),
                            severity: rule.severity.clone(),
                            target: "dockerfile.final_stage.USER".to_string(),
                            reason: "final stage USER resolves to root".to_string(),
                        });
                        patches.push(PatchOperation {
                            op: "replace_instruction".to_string(),
                            path: "dockerfile.final_stage.USER".to_string(),
                            value: JsonValue::String("USER 65532:65532".to_string()),
                            rule_id: rule.id.clone(),
                        });
                    }
                    None => {
                        violations.push(PolicyViolation {
                            rule_id: rule.id.clone(),
                            severity: rule.severity.clone(),
                            target: "dockerfile.final_stage.USER".to_string(),
                            reason: "final stage is missing USER instruction".to_string(),
                        });
                    }
                }
            }
            PolicyAction::RequireLabels { labels } => {
                let Some(_) = parsed.final_stage_range() else {
                    for label in labels {
                        violations.push(PolicyViolation {
                            rule_id: rule.id.clone(),
                            severity: rule.severity.clone(),
                            target: format!("dockerfile.final_stage.LABEL.{label}"),
                            reason: "dockerfile has no FROM stage".to_string(),
                        });
                    }
                    continue;
                };

                let existing = extract_final_stage_labels(&parsed);
                for label in labels {
                    if existing.contains(label) {
                        continue;
                    }
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: format!("dockerfile.final_stage.LABEL.{label}"),
                        reason: format!("missing required OCI label `{label}`"),
                    });
                    patches.push(PatchOperation {
                        op: "insert_after".to_string(),
                        path: "dockerfile.final_stage.last_label_or_from".to_string(),
                        value: JsonValue::String(format!("LABEL {label}=unknown")),
                        rule_id: rule.id.clone(),
                    });
                }
            }
            PolicyAction::ForbidRuntimePackageManager => {
                let Some(_) = parsed.final_stage_range() else {
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: "dockerfile.final_stage.RUN".to_string(),
                        reason: "dockerfile has no FROM stage".to_string(),
                    });
                    continue;
                };

                let package_manager_re =
                    Regex::new(r"(?i)\b(apt-get|apt|apk|yum|dnf|microdnf|zypper|pacman)\b")
                        .map_err(|error| AppError::InvalidInput {
                            reason: format!("failed to compile package manager regex: {error}"),
                        })?;

                for instruction in parsed.final_stage_instructions_by_keyword("RUN") {
                    if let Some(match_) = package_manager_re.find(&instruction.arguments) {
                        violations.push(PolicyViolation {
                            rule_id: rule.id.clone(),
                            severity: rule.severity.clone(),
                            target: format!("dockerfile.final_stage.RUN.line:{}", instruction.line),
                            reason: format!(
                                "runtime package manager command detected (`{}`)",
                                match_.as_str().to_ascii_lowercase()
                            ),
                        });
                    }
                }
            }
            PolicyAction::EnsureKey { .. }
            | PolicyAction::EnsureListContains { .. }
            | PolicyAction::RequireImageDigest { .. } => {}
        }
    }

    Ok(finalize_policy_output(
        policy.domain,
        &policy.strictness,
        violations,
        patches,
    ))
}

/// Apply compose patch operations to compose YAML content.
pub fn apply_compose_patch_plan(
    compose_yaml: &str,
    patch_plan: &[PatchOperation],
) -> Result<String, AppError> {
    let mut document: YamlValue =
        serde_yaml::from_str(compose_yaml).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse compose yaml: {error}"),
        })?;

    let root = document
        .as_mapping_mut()
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose root must be a mapping".to_string(),
        })?;

    let services = root
        .get_mut(&YamlValue::String("services".to_string()))
        .and_then(YamlValue::as_mapping_mut)
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose input must include a services mapping".to_string(),
        })?;

    for patch in patch_plan {
        let (service_name, key) =
            parse_compose_service_path(&patch.path).ok_or_else(|| AppError::InvalidInput {
                reason: format!("unsupported compose patch path: {}", patch.path),
            })?;

        let service = services
            .get_mut(&YamlValue::String(service_name.to_string()))
            .and_then(YamlValue::as_mapping_mut)
            .ok_or_else(|| AppError::InvalidInput {
                reason: format!("compose service `{service_name}` not found"),
            })?;

        let value = serde_yaml::to_value(&patch.value).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to convert patch value to yaml: {error}"),
        })?;
        let key_value = YamlValue::String(key.to_string());

        match patch.op.as_str() {
            "set" => {
                service.insert(key_value, value);
            }
            "list_add" => {
                if let Some(current) = service.get_mut(&key_value) {
                    match current {
                        YamlValue::Sequence(items) => {
                            if !items.iter().any(|entry| entry == &value) {
                                items.push(value);
                            }
                        }
                        YamlValue::String(existing) => {
                            let current_value = YamlValue::String(existing.clone());
                            if current_value != value {
                                *current = YamlValue::Sequence(vec![current_value, value]);
                            }
                        }
                        _ => {
                            return Err(AppError::InvalidInput {
                                reason: format!(
                                    "list_add target is not list/string at {}",
                                    patch.path
                                ),
                            });
                        }
                    }
                } else {
                    service.insert(key_value, YamlValue::Sequence(vec![value]));
                }
            }
            _ => {
                return Err(AppError::InvalidInput {
                    reason: format!("unsupported compose patch op: {}", patch.op),
                });
            }
        }
    }

    let mut rendered =
        serde_yaml::to_string(&document).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to render compose yaml: {error}"),
        })?;
    if let Some(stripped) = rendered.strip_prefix("---\n") {
        rendered = stripped.to_string();
    }
    Ok(rendered)
}

fn finalize_policy_output(
    domain: PolicyDomain,
    strictness: &PolicyStrictness,
    mut violations: Vec<PolicyViolation>,
    mut patch_plan: Vec<PatchOperation>,
) -> PolicyEvaluation {
    violations.sort_by(|left, right| {
        (
            left.severity.rank(),
            left.rule_id.as_str(),
            left.target.as_str(),
            left.reason.as_str(),
        )
            .cmp(&(
                right.severity.rank(),
                right.rule_id.as_str(),
                right.target.as_str(),
                right.reason.as_str(),
            ))
    });

    patch_plan.sort_by(|left, right| {
        (
            left.rule_id.as_str(),
            left.path.as_str(),
            left.op.as_str(),
            left.value.to_string(),
        )
            .cmp(&(
                right.rule_id.as_str(),
                right.path.as_str(),
                right.op.as_str(),
                right.value.to_string(),
            ))
    });

    patch_plan.dedup_by(|left, right| {
        left.rule_id == right.rule_id
            && left.path == right.path
            && left.op == right.op
            && left.value == right.value
    });

    PolicyEvaluation {
        domain: domain.as_str().to_string(),
        strictness: strictness.clone(),
        violations,
        patch_plan,
    }
}

fn get_services_mapping(document: &YamlValue) -> Result<&Mapping, AppError> {
    document
        .as_mapping()
        .and_then(|mapping| mapping.get(&YamlValue::String("services".to_string())))
        .and_then(YamlValue::as_mapping)
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose input must include a services mapping".to_string(),
        })
}

fn evaluate_rule_for_service(
    rule: &PolicyRule,
    service_name: &str,
    service: &Mapping,
    cache: &CachedProfiles,
    violations: &mut Vec<PolicyViolation>,
    patches: &mut Vec<PatchOperation>,
) -> Result<(), AppError> {
    match &rule.action {
        PolicyAction::EnsureKey { key, value } => {
            let current = get_service_key(service, key);
            if current != Some(value) {
                let reason = if current.is_none() {
                    format!("missing required key `{key}`")
                } else {
                    format!("key `{key}` does not match required value")
                };
                add_compose_violation(violations, rule, service_name, key, reason);
                patches.push(PatchOperation {
                    op: "set".to_string(),
                    path: format!("services.{service_name}.{key}"),
                    value: yaml_to_json(value)?,
                    rule_id: rule.id.clone(),
                });
            }
        }
        PolicyAction::EnsureListContains { key, value } => {
            let contains = get_service_key(service, key)
                .map(|entry| yaml_list_contains(entry, value))
                .unwrap_or(false);
            if !contains {
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    key,
                    format!("list `{key}` is missing required value `{value}`"),
                );
                patches.push(PatchOperation {
                    op: "list_add".to_string(),
                    path: format!("services.{service_name}.{key}"),
                    value: JsonValue::String(value.clone()),
                    rule_id: rule.id.clone(),
                });
            }
        }
        PolicyAction::RequireImageDigest { key } => {
            let Some(image) = get_service_key(service, key).and_then(yaml_scalar_to_string) else {
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    key,
                    "missing image reference".to_string(),
                );
                return Ok(());
            };

            if has_digest_pin(&image) {
                return Ok(());
            }

            match lookup_digest_for_image(cache, &image) {
                Some(digest) => {
                    add_compose_violation(
                        violations,
                        rule,
                        service_name,
                        key,
                        "image is not pinned by digest".to_string(),
                    );
                    patches.push(PatchOperation {
                        op: "set".to_string(),
                        path: format!("services.{service_name}.{key}"),
                        value: JsonValue::String(pin_image_with_digest(&image, &digest)),
                        rule_id: rule.id.clone(),
                    });
                }
                None => {
                    add_compose_violation(
                        violations,
                        rule,
                        service_name,
                        key,
                        "image not pinned by digest and no digest found in cache".to_string(),
                    );
                }
            }
        }
        PolicyAction::RequireNonRootUser { key } => {
            let current_user = get_service_key(service, key).and_then(yaml_scalar_to_string);
            if current_user
                .as_deref()
                .is_some_and(|user| !is_root_user(user))
            {
                return Ok(());
            }

            let image = get_service_key(service, "image").and_then(yaml_scalar_to_string);
            let runtime_user = image
                .as_deref()
                .and_then(|reference| lookup_runtime_user_for_image(cache, reference));

            match runtime_user {
                Some(user) if !is_root_user(&user) => {
                    add_compose_violation(
                        violations,
                        rule,
                        service_name,
                        key,
                        "service user is root or unset; using non-root image runtime user"
                            .to_string(),
                    );
                    patches.push(PatchOperation {
                        op: "set".to_string(),
                        path: format!("services.{service_name}.{key}"),
                        value: JsonValue::String(user),
                        rule_id: rule.id.clone(),
                    });
                }
                Some(_) => {
                    add_compose_violation(
                        violations,
                        rule,
                        service_name,
                        key,
                        "image runtime user is root; derivative image required".to_string(),
                    );
                }
                None => {
                    add_compose_violation(
                        violations,
                        rule,
                        service_name,
                        key,
                        "image runtime user unknown; derivative image or explicit exception required"
                            .to_string(),
                    );
                }
            }
        }
        PolicyAction::RequireMultiStage
        | PolicyAction::RequireLabels { .. }
        | PolicyAction::ForbidRuntimePackageManager => {}
    }
    Ok(())
}

fn add_compose_violation(
    violations: &mut Vec<PolicyViolation>,
    rule: &PolicyRule,
    service_name: &str,
    key: &str,
    reason: String,
) {
    violations.push(PolicyViolation {
        rule_id: rule.id.clone(),
        severity: rule.severity.clone(),
        target: format!("services.{service_name}.{key}"),
        reason,
    });
}

fn get_service_key<'a>(service: &'a Mapping, key: &str) -> Option<&'a YamlValue> {
    service.get(&YamlValue::String(key.to_string()))
}

fn yaml_to_json(value: &YamlValue) -> Result<JsonValue, AppError> {
    serde_json::to_value(value).map_err(|error| AppError::InvalidInput {
        reason: format!("failed to convert policy value to json: {error}"),
    })
}

fn yaml_list_contains(value: &YamlValue, expected: &str) -> bool {
    match value {
        YamlValue::Sequence(items) => items
            .iter()
            .filter_map(yaml_scalar_to_string)
            .any(|entry| entry == expected),
        YamlValue::String(item) => item == expected,
        _ => false,
    }
}

fn yaml_scalar_to_string(value: &YamlValue) -> Option<String> {
    match value {
        YamlValue::String(text) => Some(text.to_string()),
        YamlValue::Number(number) => Some(number.to_string()),
        _ => None,
    }
}

fn has_digest_pin(image: &str) -> bool {
    image.split_once('@').is_some_and(|(_, digest)| {
        digest
            .get(0..7)
            .is_some_and(|prefix| prefix.eq_ignore_ascii_case("sha256:"))
    })
}

fn pin_image_with_digest(image: &str, digest: &str) -> String {
    let base = image.split_once('@').map(|(head, _)| head).unwrap_or(image);
    format!("{base}@{digest}")
}

fn lookup_digest_for_image(cache: &CachedProfiles, image: &str) -> Option<String> {
    let normalized = normalize_image_reference(image).ok()?;
    let normalized_base = normalized
        .split_once('@')
        .map(|(head, _)| head)
        .unwrap_or(normalized.as_str());

    let mut candidates: BTreeMap<String, String> = BTreeMap::new();
    for profile in &cache.profiles {
        let profile_base = profile
            .image
            .split_once('@')
            .map(|(head, _)| head)
            .unwrap_or(&profile.image);
        if normalized_base == profile_base {
            if let Some(digest) = &profile.digest {
                candidates.insert(profile.id.clone(), digest.clone());
            }
        }
    }
    candidates.into_values().next()
}

fn lookup_runtime_user_for_image(cache: &CachedProfiles, image: &str) -> Option<String> {
    let normalized = normalize_image_reference(image).ok()?;
    let normalized_base = normalized
        .split_once('@')
        .map(|(head, _)| head)
        .unwrap_or(normalized.as_str());

    let mut candidates: BTreeMap<String, String> = BTreeMap::new();
    for profile in &cache.profiles {
        let profile_base = profile
            .image
            .split_once('@')
            .map(|(head, _)| head)
            .unwrap_or(&profile.image);
        if normalized_base == profile_base {
            if let Some(user) = &profile.runtime.user {
                candidates.insert(profile.id.clone(), user.clone());
            }
        }
    }
    candidates.into_values().next()
}

fn extract_final_stage_labels(parsed: &ParsedDockerfile) -> BTreeSet<String> {
    let mut labels = BTreeSet::new();
    for instruction in parsed.final_stage_instructions_by_keyword("LABEL") {
        for (label, _) in parse_label_pairs(&instruction.arguments) {
            labels.insert(label);
        }
    }
    labels
}

fn parse_user_argument(arguments: &str) -> Option<String> {
    split_quoted_tokens(arguments).into_iter().next()
}

fn parse_label_pairs(arguments: &str) -> Vec<(String, String)> {
    let mut output = Vec::new();
    for token in split_quoted_tokens(arguments) {
        if let Some((key, value)) = token.split_once('=') {
            let clean_key = trim_quotes(key);
            let clean_value = trim_quotes(value);
            if !clean_key.is_empty() {
                output.push((clean_key.to_string(), clean_value.to_string()));
            }
        }
    }
    output
}

fn split_quoted_tokens(value: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut quote: Option<char> = None;

    for ch in value.chars() {
        match quote {
            Some(active) => {
                if ch == active {
                    quote = None;
                } else {
                    current.push(ch);
                }
            }
            None => {
                if ch == '"' || ch == '\'' {
                    quote = Some(ch);
                } else if ch.is_whitespace() {
                    if !current.is_empty() {
                        tokens.push(current.clone());
                        current.clear();
                    }
                } else {
                    current.push(ch);
                }
            }
        }
    }

    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}

fn trim_quotes(value: &str) -> &str {
    value.trim().trim_matches('"').trim_matches('\'')
}

fn is_root_user(user: &str) -> bool {
    let normalized = user.trim().to_ascii_lowercase();
    normalized.is_empty()
        || normalized == "root"
        || normalized == "0"
        || normalized == "0:0"
        || normalized.starts_with("0:")
}

fn parse_compose_service_path(path: &str) -> Option<(&str, &str)> {
    if !path.starts_with("services.") {
        return None;
    }
    let remainder = path.trim_start_matches("services.");
    let (service_name, key) = remainder.split_once('.')?;
    if service_name.is_empty() || key.is_empty() || key.contains('.') {
        return None;
    }
    Some((service_name, key))
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        apply_compose_patch_plan, evaluate_compose_policy, evaluate_dockerfile_policy,
        parse_policy_pack, PatchOperation, PolicyAction, PolicyDomain, PolicyStrictness,
        RuleSeverity,
    };
    use crate::model::{CachedProfiles, ImageProfile, OciLabelProfile, Platform, RuntimeProfile};

    fn base_cache() -> CachedProfiles {
        CachedProfiles {
            schema_version: 2,
            profiles: vec![ImageProfile {
                id: "IMG-1".to_string(),
                image: "docker.io/library/nginx:1.27".to_string(),
                docs_url: None,
                dockerfile_url: None,
                digest: Some(
                    "sha256:1111111111111111111111111111111111111111111111111111111111111111"
                        .to_string(),
                ),
                platforms: vec![Platform {
                    os: "linux".to_string(),
                    arch: "amd64".to_string(),
                }],
                runtime: RuntimeProfile {
                    user: Some("1001:1001".to_string()),
                    entrypoint: Vec::new(),
                    cmd: Vec::new(),
                    working_dir: None,
                    env_keys: Vec::new(),
                    oci: OciLabelProfile::default(),
                },
                sources: Vec::new(),
                notes: Vec::new(),
            }],
            unresolved_references: Vec::new(),
        }
    }

    #[test]
    fn parse_policy_pack_compiles_typed_actions() {
        let yaml = r#"
version: 1
domain: compose
strictness: enforcing
rules:
  - id: AC-CMP-READONLY
    severity: block
    action: ensure_key
    target: service.*
    key: read_only
    value: true
"#;
        let policy = parse_policy_pack(yaml).expect("policy should parse");
        assert_eq!(policy.domain, PolicyDomain::Compose);
        assert_eq!(policy.strictness, PolicyStrictness::Enforcing);
        assert_eq!(policy.rules[0].severity, RuleSeverity::Block);
        assert!(matches!(
            policy.rules[0].action,
            PolicyAction::EnsureKey { .. }
        ));
    }

    #[test]
    fn evaluate_compose_policy_returns_sorted_violations_and_patch_plan() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: enforcing
rules:
  - id: AC-CMP-DIGEST
    severity: block
    action: require_image_digest
    target: service.*
    key: image
  - id: AC-CMP-NNP
    severity: block
    action: ensure_list_contains
    target: service.*
    key: security_opt
    value: no-new-privileges:true
"#;

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert_eq!(result.domain, "compose");
        assert_eq!(result.strictness, PolicyStrictness::Enforcing);
        assert_eq!(result.violations.len(), 2);
        assert_eq!(result.patch_plan.len(), 2);
    }

    #[test]
    fn evaluate_dockerfile_policy_reports_expected_violations_and_patch_ops() {
        let dockerfile = r#"
FROM debian:12
RUN apt-get update && apt-get install -y curl
USER root
"#;
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-MULTISTAGE
    severity: block
    action: require_multi_stage
    target: dockerfile
  - id: AC-DF-USER
    severity: block
    action: require_non_root_user
    target: final_stage
    key: USER
  - id: AC-DF-PACKAGE-MGR
    severity: block
    action: forbid_runtime_package_manager
    target: final_stage
"#;

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert_eq!(result.domain, "dockerfile");
        assert!(result
            .violations
            .iter()
            .any(|violation| violation.rule_id == "AC-DF-MULTISTAGE"));
        assert!(result
            .violations
            .iter()
            .any(|violation| violation.rule_id == "AC-DF-USER"));
        assert!(result
            .violations
            .iter()
            .any(|violation| violation.rule_id == "AC-DF-PACKAGE-MGR"));
        assert!(result
            .patch_plan
            .iter()
            .any(|patch| patch.op == "replace_instruction"));
    }

    #[test]
    fn apply_compose_patch_plan_updates_compose_yaml() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
"#;
        let plan = vec![
            PatchOperation {
                op: "set".to_string(),
                path: "services.web.read_only".to_string(),
                value: json!(true),
                rule_id: "AC-CMP-READONLY".to_string(),
            },
            PatchOperation {
                op: "list_add".to_string(),
                path: "services.web.security_opt".to_string(),
                value: json!("no-new-privileges:true"),
                rule_id: "AC-CMP-NNP".to_string(),
            },
        ];

        let patched = apply_compose_patch_plan(compose, &plan).expect("patch apply should work");
        assert!(patched.contains("read_only: true"));
        assert!(patched.contains("security_opt:"));
        assert!(patched.contains("no-new-privileges:true"));
    }
}
