//! Deterministic policy loading and evaluation for compose and Dockerfile workflows.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Component, Path, PathBuf};

use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use serde_yaml::{Mapping, Value as YamlValue};

use crate::dockerfile::ParsedDockerfile;
use crate::error::AppError;
use crate::fetch::normalize_image_reference;
use crate::heuristics::{self, DeployMode};
use crate::model::{CachedProfiles, ImageProfile};
use crate::read_utf8_file_with_size_limit;

const MAX_YAML_MERGE_DEPTH: u8 = 128;

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
    /// Forbid a top-level service key in compose services.
    ForbidKey { key: String },
    /// Ensure deterministic volume permission init sidecars for non-root writable services.
    EnsureVolumePermissions,
    /// Synthesize deterministic healthchecks from runtime facts/knowledge.
    SynthesizeHealthcheck,
    /// Ensure writable tmpfs/volume paths exist when read-only rootfs is used.
    EnsureWritablePaths,
    /// Apply deterministic capability/device reservation heuristics.
    EnsureCapabilityProfile,
    /// Ensure mode-aware deterministic resource limits.
    EnsureResourceLimits {
        /// Deployment mode (`compose` or `swarm`).
        mode: DeployMode,
        /// Memory limit value.
        memory: String,
        /// CPU limit value.
        cpus: String,
        /// PID limit used in compose mode.
        pids_limit: u64,
    },
    /// Require sensitive environment values to be sourced via compose secrets.
    RequireSensitiveEnvSecrets,
    /// Require all Dockerfile FROM references to be digest-pinned.
    RequireFromDigest,
    /// Require Dockerfile ARG declarations for reproducibility or traceability.
    RequireBuildArg { key: String },
    /// Require cache mounts on apt/cargo RUN instructions.
    RequireBuildCacheMounts,
    /// Require final-stage SUID/SGID stripping for hardened runtime images.
    RequireSuidSgidStrip,
    /// Require a final-stage HEALTHCHECK instruction.
    RequireHealthcheck,
    /// Require a companion file next to the source Dockerfile (for example `.dockerignore`).
    RequireCompanionFile { key: String },
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
    /// - compose: `set`, `set_root`, `list_add`
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

impl PolicyEvaluation {
    /// Returns `true` when at least one violation has `Block` severity.
    pub fn has_blocked_violations(&self) -> bool {
        self.violations
            .iter()
            .any(|violation| violation.severity == RuleSeverity::Block)
    }
}

const MAX_YAML_PATH_SEGMENTS: usize = 64;
const MAX_YAML_PATH_INDEX: usize = 4096;
const YAML_MERGE_KEY: &str = "<<";
pub(crate) const MAX_POLICY_PACK_BYTES: u64 = 1_048_576;
// Dockerfile patch paths are domain-specific sentinels emitted for human-guidance
// patch plans. They are not YAML/compose paths and must be rejected by compose
// patch application.
const DOCKERFILE_PATCH_SENTINEL_HEADER: &str = "dockerfile.header";
const DOCKERFILE_PATCH_SENTINEL_FINAL_STAGE_LAST_RUN_OR_FROM: &str =
    "dockerfile.final_stage.last_run_or_from";

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
    mode: Option<String>,
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
    load_policy_pack_with_limit(policy_path, expected_domain, MAX_POLICY_PACK_BYTES)
}

/// Load and compile a policy pack from disk with explicit file-size limit.
pub fn load_policy_pack_with_limit(
    policy_path: &Path,
    expected_domain: PolicyDomain,
    max_bytes: u64,
) -> Result<PolicyPack, AppError> {
    let text = read_utf8_file_with_size_limit(policy_path, max_bytes, "policy pack file")?;
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
        rules.push(compile_rule(raw_rule, domain)?);
    }

    Ok(PolicyPack {
        version: raw.version,
        domain,
        strictness,
        rules,
    })
}

fn compile_rule(raw: RawPolicyRule, domain: PolicyDomain) -> Result<PolicyRule, AppError> {
    let severity = RuleSeverity::parse(&raw.severity)?;
    let mode = raw.mode.unwrap_or_else(|| "compose".to_string());
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
        "forbid_key" => PolicyAction::ForbidKey {
            key: required_field(raw.key, "key", &raw.id)?,
        },
        "ensure_volume_permissions" => PolicyAction::EnsureVolumePermissions,
        "synthesize_healthcheck" => PolicyAction::SynthesizeHealthcheck,
        "ensure_writable_paths" => PolicyAction::EnsureWritablePaths,
        "ensure_capability_profile" => PolicyAction::EnsureCapabilityProfile,
        "ensure_resource_limits" => {
            let mode = DeployMode::parse(&mode)?;
            let (memory, cpus, pids_limit) = parse_resource_limit_defaults(raw.value.as_ref());
            PolicyAction::EnsureResourceLimits {
                mode,
                memory,
                cpus,
                pids_limit,
            }
        }
        "require_sensitive_env_secrets" => PolicyAction::RequireSensitiveEnvSecrets,
        "require_from_digest" => PolicyAction::RequireFromDigest,
        "require_build_arg" | "ensure_arg" => PolicyAction::RequireBuildArg {
            key: required_field(raw.key, "key", &raw.id)?,
        },
        "require_build_cache_mounts" => PolicyAction::RequireBuildCacheMounts,
        "require_suid_sgid_strip" => PolicyAction::RequireSuidSgidStrip,
        "require_healthcheck" => PolicyAction::RequireHealthcheck,
        "require_companion_file" => {
            let key = required_field(raw.key, "key", &raw.id)?;
            validate_companion_file_key(&key, &raw.id)?;
            PolicyAction::RequireCompanionFile { key }
        }
        _ => {
            return Err(AppError::InvalidInput {
                reason: format!("unsupported policy action: {}", raw.action),
            });
        }
    };

    validate_rule_action_for_domain(domain, &action, &raw.id)?;
    validate_rule_target(domain, &action, &raw.target, &raw.id)?;
    validate_rule_action_payload(&action, &raw.id)?;

    Ok(PolicyRule {
        id: raw.id,
        severity,
        action,
        target: raw.target,
        rationale: raw.rationale,
    })
}

fn validate_rule_action_for_domain(
    domain: PolicyDomain,
    action: &PolicyAction,
    rule_id: &str,
) -> Result<(), AppError> {
    let supported = match domain {
        PolicyDomain::Compose => matches!(
            action,
            PolicyAction::EnsureKey { .. }
                | PolicyAction::EnsureListContains { .. }
                | PolicyAction::RequireImageDigest { .. }
                | PolicyAction::RequireNonRootUser { .. }
                | PolicyAction::ForbidKey { .. }
                | PolicyAction::EnsureVolumePermissions
                | PolicyAction::SynthesizeHealthcheck
                | PolicyAction::EnsureWritablePaths
                | PolicyAction::EnsureCapabilityProfile
                | PolicyAction::EnsureResourceLimits { .. }
                | PolicyAction::RequireSensitiveEnvSecrets
        ),
        PolicyDomain::Dockerfile => matches!(
            action,
            PolicyAction::RequireMultiStage
                | PolicyAction::RequireNonRootUser { .. }
                | PolicyAction::RequireLabels { .. }
                | PolicyAction::ForbidRuntimePackageManager
                | PolicyAction::RequireFromDigest
                | PolicyAction::RequireBuildArg { .. }
                | PolicyAction::RequireBuildCacheMounts
                | PolicyAction::RequireSuidSgidStrip
                | PolicyAction::RequireHealthcheck
                | PolicyAction::RequireCompanionFile { .. }
        ),
    };
    if supported {
        return Ok(());
    }

    Err(AppError::InvalidInput {
        reason: format!(
            "rule {rule_id} action is not supported for {} policies",
            domain.as_str()
        ),
    })
}

fn validate_rule_target(
    domain: PolicyDomain,
    action: &PolicyAction,
    target: &str,
    rule_id: &str,
) -> Result<(), AppError> {
    let expected_targets: &[&str] = match domain {
        PolicyDomain::Compose => &["service.*"],
        PolicyDomain::Dockerfile => match action {
            PolicyAction::RequireNonRootUser { .. }
            | PolicyAction::RequireLabels { .. }
            | PolicyAction::ForbidRuntimePackageManager
            | PolicyAction::RequireSuidSgidStrip
            | PolicyAction::RequireHealthcheck => &["final_stage"],
            PolicyAction::RequireMultiStage
            | PolicyAction::RequireFromDigest
            | PolicyAction::RequireBuildArg { .. }
            | PolicyAction::RequireBuildCacheMounts
            | PolicyAction::RequireCompanionFile { .. } => &["dockerfile"],
            _ => &[],
        },
    };

    if expected_targets.contains(&target) {
        return Ok(());
    }

    let expected = if expected_targets.is_empty() {
        "<none>".to_string()
    } else {
        expected_targets.join(", ")
    };
    Err(AppError::InvalidInput {
        reason: format!(
            "rule {rule_id} has unsupported target `{target}` for {} policy/action; expected one of: {expected}",
            domain.as_str()
        ),
    })
}

fn validate_rule_action_payload(action: &PolicyAction, rule_id: &str) -> Result<(), AppError> {
    match action {
        PolicyAction::RequireLabels { labels } => {
            for label in labels {
                validate_dockerfile_label_key(label, rule_id)?;
            }
            Ok(())
        }
        PolicyAction::RequireBuildArg { key } => validate_dockerfile_build_arg_key(key, rule_id),
        PolicyAction::RequireCompanionFile { key } => validate_companion_file_key(key, rule_id),
        _ => Ok(()),
    }
}

fn validate_dockerfile_label_key(label: &str, rule_id: &str) -> Result<(), AppError> {
    if label.is_empty() {
        return Err(AppError::InvalidInput {
            reason: format!("rule {rule_id} label key must not be empty"),
        });
    }
    if label
        .chars()
        .any(|ch| ch.is_ascii_control() || ch.is_whitespace())
    {
        return Err(AppError::InvalidInput {
            reason: format!(
                "rule {rule_id} label key `{label}` must not contain control characters or whitespace"
            ),
        });
    }
    if label.contains('=') {
        return Err(AppError::InvalidInput {
            reason: format!("rule {rule_id} label key `{label}` must not contain `=`"),
        });
    }
    if !label
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-' | '/'))
    {
        return Err(AppError::InvalidInput {
            reason: format!("rule {rule_id} label key `{label}` contains unsupported characters"),
        });
    }
    Ok(())
}

fn validate_dockerfile_build_arg_key(key: &str, rule_id: &str) -> Result<(), AppError> {
    let mut chars = key.chars();
    let Some(first) = chars.next() else {
        return Err(AppError::InvalidInput {
            reason: format!("rule {rule_id} build arg key must not be empty"),
        });
    };
    if !(first.is_ascii_alphabetic() || first == '_') {
        return Err(AppError::InvalidInput {
            reason: format!(
                "rule {rule_id} build arg key `{key}` must start with ASCII letter or `_`"
            ),
        });
    }
    if !chars.all(|ch| ch.is_ascii_alphanumeric() || ch == '_') {
        return Err(AppError::InvalidInput {
            reason: format!(
                "rule {rule_id} build arg key `{key}` must contain only ASCII letters, digits, or `_`"
            ),
        });
    }
    Ok(())
}

fn parse_resource_limit_defaults(value: Option<&YamlValue>) -> (String, String, u64) {
    let mut memory = "512m".to_string();
    let mut cpus = "1.0".to_string();
    let mut pids_limit = 256u64;
    let Some(YamlValue::Mapping(map)) = value else {
        return (memory, cpus, pids_limit);
    };

    if let Some(item) = map
        .get(YamlValue::String("memory".to_string()))
        .and_then(YamlValue::as_str)
    {
        memory = item.to_string();
    }
    if let Some(item) = map
        .get(YamlValue::String("cpus".to_string()))
        .and_then(YamlValue::as_str)
    {
        cpus = item.to_string();
    }
    if let Some(item) = map
        .get(YamlValue::String("pids_limit".to_string()))
        .and_then(YamlValue::as_u64)
    {
        pids_limit = item;
    }

    (memory, cpus, pids_limit)
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
    evaluate_compose_policy_with_mode(compose_yaml, cache, policy, DeployMode::Compose)
}

/// Evaluate compose input against a compose policy pack with explicit deploy mode.
pub fn evaluate_compose_policy_with_mode(
    compose_yaml: &str,
    cache: &CachedProfiles,
    policy: &PolicyPack,
    mode: DeployMode,
) -> Result<PolicyEvaluation, AppError> {
    if policy.domain != PolicyDomain::Compose {
        return Err(AppError::InvalidInput {
            reason: format!(
                "evaluate_compose_policy requires compose policy, got {}",
                policy.domain.as_str()
            ),
        });
    }

    let mut document: YamlValue =
        serde_yaml::from_str(compose_yaml).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse compose yaml: {error}"),
        })?;
    materialize_yaml_merge_keys(&mut document, MAX_YAML_MERGE_DEPTH)?;
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
        validate_rule_action_for_domain(policy.domain, &rule.action, &rule.id)?;
        validate_rule_target(policy.domain, &rule.action, &rule.target, &rule.id)?;
        validate_rule_action_payload(&rule.action, &rule.id)?;
        for service_name in &service_names {
            let service_value = services
                .get(YamlValue::String(service_name.clone()))
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
                ServiceRuleContext {
                    service_name,
                    service,
                    services,
                    cache,
                    active_mode: mode,
                },
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
    evaluate_dockerfile_policy_with_cache_and_source(dockerfile_text, policy, None, None)
}

/// Evaluate Dockerfile input against a dockerfile policy pack with optional image cache context.
pub fn evaluate_dockerfile_policy_with_cache(
    dockerfile_text: &str,
    policy: &PolicyPack,
    cache: Option<&CachedProfiles>,
) -> Result<PolicyEvaluation, AppError> {
    evaluate_dockerfile_policy_with_cache_and_source(dockerfile_text, policy, cache, None)
}

/// Evaluate Dockerfile input against a dockerfile policy pack with optional cache and source path.
pub fn evaluate_dockerfile_policy_with_cache_and_source(
    dockerfile_text: &str,
    policy: &PolicyPack,
    cache: Option<&CachedProfiles>,
    source_path: Option<&Path>,
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
    let package_manager_re = Regex::new(
        r"(?i)\b(apt-get|apt|apk|yum|dnf|microdnf|zypper|pacman)\b",
    )
    .map_err(|error| AppError::InvalidInput {
        reason: format!("failed to compile package manager regex: {error}"),
    })?;

    for rule in &policy.rules {
        validate_rule_action_for_domain(policy.domain, &rule.action, &rule.id)?;
        validate_rule_target(policy.domain, &rule.action, &rule.target, &rule.id)?;
        validate_rule_action_payload(&rule.action, &rule.id)?;
        match &rule.action {
            PolicyAction::RequireMultiStage => {
                if !parsed.has_multiple_stages() {
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: "dockerfile".to_string(),
                        reason: "dockerfile is not multi-stage".to_string(),
                    });
                    // Multi-stage conversion needs workload-specific artifact boundaries.
                    // Auto-inserting a stage can silently change runtime semantics.
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
            PolicyAction::RequireFromDigest => {
                for instruction in parsed
                    .instructions()
                    .iter()
                    .filter(|instruction| instruction.keyword == "FROM")
                {
                    let Some(reference) = parse_from_reference(&instruction.arguments) else {
                        continue;
                    };
                    if is_digest_exempt_from_reference(&reference) {
                        continue;
                    }
                    if has_valid_digest_pin(&reference) {
                        continue;
                    }
                    let marker_present = has_digest_marker(&reference);
                    let cached_digest = cache.and_then(|cache_payload| {
                        lookup_digest_for_image(cache_payload, &reference)
                    });
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: format!("dockerfile.FROM.line:{}", instruction.line),
                        reason: if marker_present {
                            format!(
                                "FROM reference `{reference}` has an invalid sha256 digest (expected 64 hex characters)"
                            )
                        } else {
                            format!("FROM reference `{reference}` is not digest-pinned")
                        },
                    });
                    let replacement = pin_from_instruction_arguments(
                        &instruction.arguments,
                        cached_digest.as_deref(),
                    )
                    .unwrap_or_else(|| match cached_digest.as_deref() {
                        Some(digest) => {
                            format!("FROM {}", pin_image_with_digest(&reference, digest))
                        }
                        None => format!(
                            "FROM {}",
                            pin_image_with_digest(&reference, "sha256:<resolve-required>")
                        ),
                    });
                    patches.push(PatchOperation {
                        op: "replace_instruction".to_string(),
                        path: format!("dockerfile.FROM.line:{}", instruction.line),
                        value: JsonValue::String(replacement),
                        rule_id: rule.id.clone(),
                    });
                }
            }
            PolicyAction::RequireBuildArg { key } => {
                let arg_present = parsed
                    .instructions()
                    .iter()
                    .filter(|instruction| instruction.keyword == "ARG")
                    .filter_map(|instruction| parse_arg_name(&instruction.arguments))
                    .any(|candidate| candidate.eq_ignore_ascii_case(key));
                if arg_present {
                    continue;
                }

                violations.push(PolicyViolation {
                    rule_id: rule.id.clone(),
                    severity: rule.severity.clone(),
                    target: format!("dockerfile.ARG.{key}"),
                    reason: format!("dockerfile is missing required build argument `{key}`"),
                });
                patches.push(PatchOperation {
                    op: "insert_after".to_string(),
                    path: DOCKERFILE_PATCH_SENTINEL_HEADER.to_string(),
                    value: JsonValue::String(format!("ARG {key}")),
                    rule_id: rule.id.clone(),
                });
            }
            PolicyAction::RequireBuildCacheMounts => {
                for instruction in parsed
                    .instructions()
                    .iter()
                    .filter(|instruction| instruction.keyword == "RUN")
                {
                    let lower = instruction.arguments.to_ascii_lowercase();
                    let needs_cache = lower.contains("apt-get")
                        || lower.contains("apt ")
                        || lower.contains("cargo build")
                        || lower.contains("cargo install");
                    if !needs_cache || lower.contains("--mount=type=cache") {
                        continue;
                    }
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: format!("dockerfile.RUN.line:{}", instruction.line),
                        reason: "RUN instruction should use BuildKit cache mount for deterministic layer hygiene"
                            .to_string(),
                    });
                    patches.push(PatchOperation {
                        op: "insert_after".to_string(),
                        path: format!("dockerfile.RUN.line:{}", instruction.line),
                        value: JsonValue::String(
                            "# add --mount=type=cache,target=/var/cache/apt for apt and /usr/local/cargo/registry for cargo"
                                .to_string(),
                        ),
                        rule_id: rule.id.clone(),
                    });
                }
            }
            PolicyAction::RequireSuidSgidStrip => {
                let Some(_) = parsed.final_stage_range() else {
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: "dockerfile.final_stage.RUN".to_string(),
                        reason: "dockerfile has no FROM stage".to_string(),
                    });
                    continue;
                };

                if has_suid_sgid_strip_in_final_stage(&parsed) {
                    continue;
                }

                violations.push(PolicyViolation {
                    rule_id: rule.id.clone(),
                    severity: rule.severity.clone(),
                    target: "dockerfile.final_stage.RUN.suid_sgid_strip".to_string(),
                    reason:
                        "final stage is missing SUID/SGID stripping command for hardened runtime"
                            .to_string(),
                });
                patches.push(PatchOperation {
                    op: "insert_after".to_string(),
                    path: DOCKERFILE_PATCH_SENTINEL_FINAL_STAGE_LAST_RUN_OR_FROM.to_string(),
                    value: JsonValue::String(
                        "RUN find / -xdev -type f \\( -perm -4000 -o -perm -2000 \\) -exec chmod a-s {} +"
                            .to_string(),
                    ),
                    rule_id: rule.id.clone(),
                });
            }
            PolicyAction::RequireHealthcheck => {
                let Some(_) = parsed.final_stage_range() else {
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: "dockerfile.final_stage.HEALTHCHECK".to_string(),
                        reason: "dockerfile has no FROM stage".to_string(),
                    });
                    continue;
                };

                if !parsed
                    .final_stage_instructions_by_keyword("HEALTHCHECK")
                    .is_empty()
                {
                    continue;
                }

                violations.push(PolicyViolation {
                    rule_id: rule.id.clone(),
                    severity: rule.severity.clone(),
                    target: "dockerfile.final_stage.HEALTHCHECK".to_string(),
                    reason: "final stage is missing HEALTHCHECK instruction".to_string(),
                });
                if policy.strictness == PolicyStrictness::Enforcing {
                    // Enforcing mode is fail-closed: do not emit placeholder guidance
                    // that could be mistaken for a complete remediation.
                    continue;
                }
                patches.push(PatchOperation {
                    op: "insert_after".to_string(),
                    path: DOCKERFILE_PATCH_SENTINEL_FINAL_STAGE_LAST_RUN_OR_FROM.to_string(),
                    value: JsonValue::String(
                        "# AC-DF-HEALTHCHECK: add a service-specific HEALTHCHECK instruction"
                            .to_string(),
                    ),
                    rule_id: rule.id.clone(),
                });
            }
            PolicyAction::RequireCompanionFile { key } => {
                let Some(path) = source_path else {
                    violations.push(PolicyViolation {
                        rule_id: rule.id.clone(),
                        severity: rule.severity.clone(),
                        target: format!("dockerfile.companion_file[{key}]"),
                        reason: format!(
                            "cannot verify companion file `{key}` without a Dockerfile source path"
                        ),
                    });
                    if policy.strictness == PolicyStrictness::Enforcing {
                        // Enforcing mode is fail-closed: report the violation but avoid
                        // placeholder patches that could be mistaken for complete remediation.
                        continue;
                    }
                    patches.push(PatchOperation {
                        op: "insert_after".to_string(),
                        path: DOCKERFILE_PATCH_SENTINEL_HEADER.to_string(),
                        value: JsonValue::String(format!(
                            "# {}: create `{key}` next to Dockerfile",
                            rule.id
                        )),
                        rule_id: rule.id.clone(),
                    });
                    continue;
                };

                let canonical_source_path =
                    fs::canonicalize(path).map_err(|error| AppError::InvalidInput {
                        reason: format!(
                            "failed to canonicalize Dockerfile source path `{}`: {error}",
                            path.display()
                        ),
                    })?;
                let companion_path = resolve_companion_file_path(&canonical_source_path, key);
                if companion_path.exists() {
                    continue;
                }

                violations.push(PolicyViolation {
                    rule_id: rule.id.clone(),
                    severity: rule.severity.clone(),
                    target: format!("dockerfile.companion_file[{key}]"),
                    reason: format!("missing companion file `{key}`"),
                });
                patches.push(PatchOperation {
                    op: "insert_after".to_string(),
                    path: DOCKERFILE_PATCH_SENTINEL_HEADER.to_string(),
                    value: JsonValue::String(format!(
                        "# {}: create `{key}` next to Dockerfile",
                        rule.id
                    )),
                    rule_id: rule.id.clone(),
                });
            }
            PolicyAction::EnsureKey { .. }
            | PolicyAction::EnsureListContains { .. }
            | PolicyAction::RequireImageDigest { .. }
            | PolicyAction::ForbidKey { .. }
            | PolicyAction::EnsureVolumePermissions
            | PolicyAction::SynthesizeHealthcheck
            | PolicyAction::EnsureWritablePaths
            | PolicyAction::EnsureCapabilityProfile
            | PolicyAction::EnsureResourceLimits { .. }
            | PolicyAction::RequireSensitiveEnvSecrets => {}
        }
    }

    Ok(finalize_policy_output(
        policy.domain,
        &policy.strictness,
        violations,
        patches,
    ))
}

/// Apply dockerfile patch operations to Dockerfile content.
pub fn apply_dockerfile_patch_plan(
    dockerfile_text: &str,
    patch_plan: &[PatchOperation],
) -> Result<String, AppError> {
    if patch_plan.is_empty() {
        return Ok(dockerfile_text.to_string());
    }

    let parsed = ParsedDockerfile::parse(dockerfile_text)?;
    let source_lines: Vec<String> = dockerfile_text.lines().map(str::to_string).collect();
    let preserve_trailing_newline = dockerfile_text.ends_with('\n');
    let mut header_inserts: Vec<String> = Vec::new();
    let mut line_replacements: BTreeMap<usize, String> = BTreeMap::new();
    let mut line_inserts: BTreeMap<usize, Vec<String>> = BTreeMap::new();

    for patch in patch_plan {
        match patch.op.as_str() {
            "insert_after" => {
                let value = patch.value.as_str().ok_or_else(|| AppError::InvalidInput {
                    reason: format!(
                        "dockerfile patch value must be string for op insert_after: {}",
                        patch.rule_id
                    ),
                })?;
                if patch.path == DOCKERFILE_PATCH_SENTINEL_HEADER {
                    header_inserts.push(value.to_string());
                    continue;
                }

                let line = if patch.path == "dockerfile.final_stage.last_label_or_from" {
                    final_stage_last_label_or_from_line(&parsed)?
                } else if patch.path == DOCKERFILE_PATCH_SENTINEL_FINAL_STAGE_LAST_RUN_OR_FROM {
                    final_stage_last_run_or_from_line(&parsed)?
                } else if let Some((keyword, line)) =
                    parse_dockerfile_instruction_line_path(&patch.path)
                {
                    if !dockerfile_has_instruction_at_line(&parsed, line, &keyword) {
                        return Err(AppError::InvalidInput {
                            reason: format!(
                                "dockerfile patch path does not match an instruction: {}",
                                patch.path
                            ),
                        });
                    }
                    line
                } else {
                    return Err(AppError::InvalidInput {
                        reason: format!(
                            "unsupported dockerfile insert_after patch path: {}",
                            patch.path
                        ),
                    });
                };
                line_inserts
                    .entry(line)
                    .or_default()
                    .push(value.to_string());
            }
            "replace_instruction" => {
                let value = patch.value.as_str().ok_or_else(|| AppError::InvalidInput {
                    reason: format!(
                        "dockerfile patch value must be string for op replace_instruction: {}",
                        patch.rule_id
                    ),
                })?;
                let line = if patch.path == "dockerfile.final_stage.USER" {
                    final_stage_user_line(&parsed)?
                } else if let Some((keyword, line)) =
                    parse_dockerfile_instruction_line_path(&patch.path)
                {
                    if !dockerfile_has_instruction_at_line(&parsed, line, &keyword) {
                        return Err(AppError::InvalidInput {
                            reason: format!(
                                "dockerfile patch path does not match an instruction: {}",
                                patch.path
                            ),
                        });
                    }
                    line
                } else {
                    return Err(AppError::InvalidInput {
                        reason: format!(
                            "unsupported dockerfile replace_instruction patch path: {}",
                            patch.path
                        ),
                    });
                };
                line_replacements.insert(line, value.to_string());
            }
            other => {
                return Err(AppError::InvalidInput {
                    reason: format!("unsupported dockerfile patch operation: {other}"),
                });
            }
        }
    }

    let header_insert_before_line = dockerfile_header_insert_before_line(&source_lines);
    let mut rendered_lines: Vec<String> = Vec::new();
    for (index, source_line) in source_lines.iter().enumerate() {
        let line_no = index + 1;
        if line_no == header_insert_before_line {
            for value in &header_inserts {
                append_patch_lines(&mut rendered_lines, value);
            }
        }
        if let Some(replacement) = line_replacements.get(&line_no) {
            rendered_lines.push(replacement.clone());
        } else {
            rendered_lines.push(source_line.clone());
        }
        if let Some(inserts) = line_inserts.get(&line_no) {
            for value in inserts {
                append_patch_lines(&mut rendered_lines, value);
            }
        }
    }
    if header_insert_before_line > source_lines.len() {
        for value in &header_inserts {
            append_patch_lines(&mut rendered_lines, value);
        }
    }

    if rendered_lines.is_empty() {
        return Ok(String::new());
    }

    let mut output = rendered_lines.join("\n");
    if preserve_trailing_newline {
        output.push('\n');
    }
    Ok(output)
}

/// Apply compose patch operations to compose YAML content.
pub fn apply_compose_patch_plan(
    compose_yaml: &str,
    patch_plan: &[PatchOperation],
    _mode: DeployMode,
) -> Result<String, AppError> {
    if patch_plan.is_empty() {
        return Ok(compose_yaml.to_string());
    }

    let mut document: YamlValue =
        serde_yaml::from_str(compose_yaml).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to parse compose yaml: {error}"),
        })?;

    if !document.is_mapping() {
        return Err(AppError::InvalidInput {
            reason: "compose root must be a mapping".to_string(),
        });
    }

    for patch in patch_plan {
        if patch.path.starts_with("dockerfile.") {
            return Err(AppError::InvalidInput {
                reason: format!(
                    "compose patch apply does not accept dockerfile sentinel path `{}`",
                    patch.path
                ),
            });
        }
        if patch.op == "inject_service" {
            let service_name = parse_compose_service_root_path(&patch.path).ok_or_else(|| {
                AppError::InvalidInput {
                    reason: format!("unsupported compose inject path: {}", patch.path),
                }
            })?;
            let patch_value =
                serde_yaml::to_value(&patch.value).map_err(|error| AppError::InvalidInput {
                    reason: format!("failed to convert patch value to yaml: {error}"),
                })?;
            let patch_mapping = patch_value
                .as_mapping()
                .ok_or_else(|| AppError::InvalidInput {
                    reason: format!("inject_service value must be a mapping at {}", patch.path),
                })?;
            let services = ensure_services_mapping_mut(&mut document)?;
            services.insert(
                YamlValue::String(service_name.to_string()),
                YamlValue::Mapping(patch_mapping.clone()),
            );
            continue;
        }

        let patch_value =
            serde_yaml::to_value(&patch.value).map_err(|error| AppError::InvalidInput {
                reason: format!("failed to convert patch value to yaml: {error}"),
            })?;

        if patch.op == "set_root" {
            let path = parse_yaml_path(&patch.path)?;
            set_yaml_value(&mut document, &path, patch_value)?;
            continue;
        }

        let (service_name, subpath) =
            parse_compose_service_path(&patch.path).ok_or_else(|| AppError::InvalidInput {
                reason: format!("unsupported compose patch path: {}", patch.path),
            })?;
        let path = parse_yaml_path(subpath)?;
        let services = ensure_services_mapping_mut(&mut document)?;
        let service_key = YamlValue::String(service_name.to_string());
        let service = services
            .get_mut(&service_key)
            .ok_or_else(|| AppError::InvalidInput {
                reason: format!("compose service `{service_name}` not found"),
            })?;

        match patch.op.as_str() {
            "set" => {
                set_yaml_value(service, &path, patch_value)?;
            }
            "list_add" => {
                list_add_yaml_value(service, &path, patch_value, &patch.path)?;
            }
            "remove" => {
                remove_yaml_value(service, &path)?;
            }
            "depends_on_add" => {
                let (_, dependency) =
                    parse_depends_on_service_path(&patch.path).ok_or_else(|| {
                        AppError::InvalidInput {
                            reason: format!(
                                "depends_on_add requires path services.<service>.depends_on.<dependency>, got {}",
                                patch.path
                            ),
                        }
                    })?;
                depends_on_add_yaml_value(service, dependency, patch_value)?;
            }
            _ => {
                return Err(AppError::InvalidInput {
                    reason: format!("unsupported compose patch op: {}", patch.op),
                });
            }
        }
    }

    canonicalize_yaml(&mut document);
    let mut rendered =
        serde_yaml::to_string(&document).map_err(|error| AppError::InvalidInput {
            reason: format!("failed to render compose yaml: {error}"),
        })?;
    if let Some(stripped) = rendered.strip_prefix("---\n") {
        rendered = stripped.to_string();
    }
    Ok(rendered)
}

fn append_patch_lines(target: &mut Vec<String>, value: &str) {
    if value.is_empty() {
        target.push(String::new());
        return;
    }
    for line in value.lines() {
        target.push(line.to_string());
    }
}

fn dockerfile_header_insert_before_line(source_lines: &[String]) -> usize {
    for (index, line) in source_lines.iter().enumerate() {
        let trimmed = line.trim_start();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        return index + 1;
    }
    source_lines.len() + 1
}

fn parse_dockerfile_instruction_line_path(path: &str) -> Option<(String, usize)> {
    let remainder = path.strip_prefix("dockerfile.")?;
    let (keyword, line_raw) = remainder.split_once(".line:")?;
    if keyword.is_empty() {
        return None;
    }
    let line = line_raw.parse::<usize>().ok()?;
    if line == 0 {
        return None;
    }
    Some((keyword.to_ascii_uppercase(), line))
}

fn dockerfile_has_instruction_at_line(
    parsed: &ParsedDockerfile,
    line: usize,
    keyword: &str,
) -> bool {
    parsed
        .instructions()
        .iter()
        .any(|instruction| instruction.line == line && instruction.keyword == keyword)
}

fn final_stage_from_line(parsed: &ParsedDockerfile) -> Result<usize, AppError> {
    parsed
        .final_stage_from_instruction()
        .map(|instruction| instruction.line)
        .ok_or_else(|| AppError::InvalidInput {
            reason: "dockerfile has no FROM stage".to_string(),
        })
}

fn final_stage_last_label_or_from_line(parsed: &ParsedDockerfile) -> Result<usize, AppError> {
    Ok(parsed
        .final_stage_instructions_by_keyword("LABEL")
        .last()
        .map(|instruction| instruction.line)
        .unwrap_or(final_stage_from_line(parsed)?))
}

fn final_stage_last_run_or_from_line(parsed: &ParsedDockerfile) -> Result<usize, AppError> {
    Ok(parsed
        .last_instruction_in_final_stage("RUN")
        .map(|instruction| instruction.line)
        .unwrap_or(final_stage_from_line(parsed)?))
}

fn final_stage_user_line(parsed: &ParsedDockerfile) -> Result<usize, AppError> {
    parsed
        .last_instruction_in_final_stage("USER")
        .map(|instruction| instruction.line)
        .ok_or_else(|| AppError::InvalidInput {
            reason: "final stage is missing USER instruction for replacement".to_string(),
        })
}

fn ensure_services_mapping_mut(document: &mut YamlValue) -> Result<&mut Mapping, AppError> {
    let root = document
        .as_mapping_mut()
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose root must be a mapping".to_string(),
        })?;
    let services = root
        .entry(YamlValue::String("services".to_string()))
        .or_insert_with(|| YamlValue::Mapping(Mapping::new()));
    services
        .as_mapping_mut()
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose input must include a services mapping".to_string(),
        })
}

fn canonicalize_yaml(value: &mut YamlValue) {
    match value {
        YamlValue::Mapping(mapping) => {
            for child in mapping.values_mut() {
                canonicalize_yaml(child);
            }
            let mut entries: Vec<(YamlValue, YamlValue)> =
                std::mem::take(mapping).into_iter().collect();
            entries.sort_by(|(left, _), (right, _)| {
                yaml_key_sort_key(left).cmp(&yaml_key_sort_key(right))
            });
            for (key, child) in entries {
                mapping.insert(key, child);
            }
        }
        YamlValue::Sequence(sequence) => {
            for child in sequence {
                canonicalize_yaml(child);
            }
        }
        _ => {}
    }
}

fn yaml_key_sort_key(value: &YamlValue) -> String {
    match value {
        YamlValue::String(text) => text.clone(),
        YamlValue::Number(number) => number.to_string(),
        YamlValue::Bool(flag) => flag.to_string(),
        other => format!("{other:?}"),
    }
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
        .and_then(|mapping| mapping.get(YamlValue::String("services".to_string())))
        .and_then(YamlValue::as_mapping)
        .ok_or_else(|| AppError::InvalidInput {
            reason: "compose input must include a services mapping".to_string(),
        })
}

fn materialize_yaml_merge_keys(value: &mut YamlValue, depth_remaining: u8) -> Result<(), AppError> {
    if depth_remaining == 0 {
        return Err(AppError::InvalidInput {
            reason: "compose yaml nesting depth exceeded".to_string(),
        });
    }
    let next_depth = depth_remaining - 1;

    match value {
        YamlValue::Mapping(mapping) => {
            let merge_key = YamlValue::String(YAML_MERGE_KEY.to_string());
            let merge_value = mapping.remove(&merge_key);

            for child in mapping.values_mut() {
                materialize_yaml_merge_keys(child, next_depth)?;
            }

            let Some(mut merge_value) = merge_value else {
                return Ok(());
            };

            materialize_yaml_merge_keys(&mut merge_value, next_depth)?;
            let source_mappings = parse_yaml_merge_sources(merge_value)?;
            let mut merged = Mapping::new();

            // YAML merge precedence keeps earlier sequence entries authoritative.
            for source in source_mappings.into_iter().rev() {
                for (key, source_value) in source {
                    merged.insert(key, source_value);
                }
            }

            for (key, explicit_value) in std::mem::take(mapping) {
                merged.insert(key, explicit_value);
            }
            *mapping = merged;
            Ok(())
        }
        YamlValue::Sequence(items) => {
            for item in items {
                materialize_yaml_merge_keys(item, next_depth)?;
            }
            Ok(())
        }
        YamlValue::Tagged(tagged) => materialize_yaml_merge_keys(&mut tagged.value, next_depth),
        _ => Ok(()),
    }
}

fn parse_yaml_merge_sources(merge_value: YamlValue) -> Result<Vec<Mapping>, AppError> {
    match merge_value {
        YamlValue::Mapping(mapping) => Ok(vec![mapping]),
        YamlValue::Sequence(items) => {
            let mut mappings = Vec::new();
            for item in items {
                match item {
                    YamlValue::Mapping(mapping) => mappings.push(mapping),
                    _ => {
                        return Err(AppError::InvalidInput {
                            reason: "compose merge key `<<` must reference a mapping or sequence of mappings"
                                .to_string(),
                        });
                    }
                }
            }
            Ok(mappings)
        }
        _ => Err(AppError::InvalidInput {
            reason: "compose merge key `<<` must reference a mapping or sequence of mappings"
                .to_string(),
        }),
    }
}

struct ServiceRuleContext<'a> {
    service_name: &'a str,
    service: &'a Mapping,
    services: &'a Mapping,
    cache: &'a CachedProfiles,
    active_mode: DeployMode,
}

fn evaluate_rule_for_service(
    rule: &PolicyRule,
    context: ServiceRuleContext<'_>,
    violations: &mut Vec<PolicyViolation>,
    patches: &mut Vec<PatchOperation>,
) -> Result<(), AppError> {
    let ServiceRuleContext {
        service_name,
        service,
        services,
        cache,
        active_mode,
    } = context;
    let service_profile = lookup_profile_for_service(cache, service);
    match &rule.action {
        PolicyAction::EnsureKey { key, value } => {
            // Init-perms sidecars (names ending in `-init-perms`) are exempt from
            // EnsureKey and RequireNonRootUser checks only. All other policy actions
            // (e.g. RequireImageDigest, SynthesizeHealthcheck) still evaluate normally.
            if is_init_permissions_service_name(service_name) {
                return Ok(());
            }
            let current = get_service_path(service, key)?;
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
            let contains = get_service_path(service, key)?
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
            let Some(image) = get_service_path(service, key)?.and_then(yaml_scalar_to_string)
            else {
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    key,
                    "missing image reference".to_string(),
                );
                return Ok(());
            };

            if has_valid_digest_pin(&image) {
                return Ok(());
            }
            let marker_present = has_digest_marker(&image);

            match lookup_digest_for_image(cache, &image) {
                Some(digest) => {
                    add_compose_violation(
                        violations,
                        rule,
                        service_name,
                        key,
                        if marker_present {
                            "image digest pin is invalid (expected sha256 with 64 hex characters)"
                                .to_string()
                        } else {
                            "image is not pinned by digest".to_string()
                        },
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
                        if marker_present {
                            "image digest pin is invalid and no valid digest was found in cache"
                                .to_string()
                        } else {
                            "image not pinned by digest and no digest found in cache".to_string()
                        },
                    );
                }
            }
        }
        PolicyAction::RequireNonRootUser { key } => {
            // Init-perms sidecar exemption — see EnsureKey comment above.
            if is_init_permissions_service_name(service_name) {
                return Ok(());
            }
            let current_user = get_service_path(service, key)?.and_then(yaml_scalar_to_string);
            if current_user
                .as_deref()
                .is_some_and(|user| !is_root_user(user))
            {
                return Ok(());
            }

            let image = get_service_path(service, "image")?.and_then(yaml_scalar_to_string);
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
        PolicyAction::ForbidKey { key } => {
            if get_service_path(service, key)?.is_some() {
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    key,
                    format!("forbidden key `{key}` is present"),
                );
                patches.push(PatchOperation {
                    op: "remove".to_string(),
                    path: format!("services.{service_name}.{key}"),
                    value: JsonValue::Null,
                    rule_id: rule.id.clone(),
                });
            }
        }
        PolicyAction::EnsureVolumePermissions => {
            if active_mode == DeployMode::Swarm {
                if matches!(rule.severity, RuleSeverity::Warn) {
                    add_compose_violation(
                        violations,
                        rule,
                        service_name,
                        "volumes",
                        "permission init sidecars are skipped in swarm mode; run a pre-deploy ownership job when required".to_string(),
                    );
                }
                return Ok(());
            }
            if service_has_permission_init_sidecar(service_name, service, services) {
                return Ok(());
            }
            for target in heuristics::bind_mount_targets(service) {
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    "volumes",
                    format!(
                        "bind mount target `{target}` detected; permission init sidecar chown is disabled by default to avoid host ownership mutation"
                    ),
                );
            }
            let synthesized =
                heuristics::ensure_volume_permissions(service_name, service, service_profile)?;
            for patch in synthesized {
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    "volumes",
                    patch.reason.clone(),
                );
                patches.push(PatchOperation {
                    op: patch.op,
                    path: patch.path,
                    value: patch.value,
                    rule_id: rule.id.clone(),
                });
            }
        }
        PolicyAction::EnsureWritablePaths => {
            let synthesized =
                heuristics::ensure_writable_paths(service_name, service, service_profile);
            for patch in synthesized {
                let target = if patch.path.starts_with("services.") {
                    if patch.path.contains(".tmpfs") {
                        "tmpfs"
                    } else {
                        "volumes"
                    }
                } else {
                    "volumes"
                };
                add_compose_violation(violations, rule, service_name, target, patch.reason.clone());
                patches.push(PatchOperation {
                    op: patch.op,
                    path: patch.path,
                    value: patch.value,
                    rule_id: rule.id.clone(),
                });
            }
        }
        PolicyAction::SynthesizeHealthcheck => {
            let synthesized =
                heuristics::synthesize_healthcheck(service_name, service, service_profile);
            for patch in synthesized {
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    "healthcheck",
                    patch.reason.clone(),
                );
                patches.push(PatchOperation {
                    op: patch.op,
                    path: patch.path,
                    value: patch.value,
                    rule_id: rule.id.clone(),
                });
            }
        }
        PolicyAction::EnsureCapabilityProfile => {
            let synthesized =
                heuristics::ensure_capability_profile(service_name, service, service_profile);
            for patch in synthesized {
                let target = if patch.path.contains("deploy.resources") {
                    "deploy.resources"
                } else {
                    "cap_add"
                };
                add_compose_violation(violations, rule, service_name, target, patch.reason.clone());
                patches.push(PatchOperation {
                    op: patch.op,
                    path: patch.path,
                    value: patch.value,
                    rule_id: rule.id.clone(),
                });
            }
        }
        PolicyAction::EnsureResourceLimits {
            mode,
            memory,
            cpus,
            pids_limit,
        } => {
            let selected_mode = match mode {
                DeployMode::Compose => active_mode,
                DeployMode::Swarm => DeployMode::Swarm,
            };
            let synthesized = heuristics::ensure_resource_limits(
                service_name,
                service,
                selected_mode,
                memory,
                cpus,
                *pids_limit,
            );
            for patch in synthesized {
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    "resources",
                    patch.reason.clone(),
                );
                patches.push(PatchOperation {
                    op: patch.op,
                    path: patch.path,
                    value: patch.value,
                    rule_id: rule.id.clone(),
                });
            }
        }
        PolicyAction::RequireSensitiveEnvSecrets => {
            let sensitive_env_keys = collect_sensitive_env_keys(service);
            if sensitive_env_keys.is_empty() {
                return Ok(());
            }
            let declared_secret_sources = collect_declared_secret_sources(service);
            for env_key in sensitive_env_keys {
                let expected_secret = secret_name_for_env_key(&env_key);
                if declared_secret_sources.contains(&expected_secret) {
                    continue;
                }
                add_compose_violation(
                    violations,
                    rule,
                    service_name,
                    "environment",
                    format!(
                        "sensitive env key `{env_key}` should be provided via compose secret `{expected_secret}` and *_FILE pattern"
                    ),
                );
            }
        }
        PolicyAction::RequireMultiStage
        | PolicyAction::RequireLabels { .. }
        | PolicyAction::ForbidRuntimePackageManager
        | PolicyAction::RequireFromDigest
        | PolicyAction::RequireBuildArg { .. }
        | PolicyAction::RequireBuildCacheMounts
        | PolicyAction::RequireSuidSgidStrip
        | PolicyAction::RequireHealthcheck
        | PolicyAction::RequireCompanionFile { .. } => {}
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

fn is_init_permissions_service_name(service_name: &str) -> bool {
    // Only sidecars that follow the explicit `<service>-init-perms` naming convention
    // are exempt from EnsureKey and RequireNonRootUser checks. Generic `init-*`
    // service names are not. Other policy actions evaluate normally for these services.
    service_name.ends_with("-init-perms")
}

fn resolve_companion_file_path(source_path: &Path, key: &str) -> PathBuf {
    // Callers should pass a canonicalized source path so companion resolution is
    // rooted at the Dockerfile directory rather than process cwd behavior.
    source_path
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join(key)
}

fn validate_companion_file_key(key: &str, rule_id: &str) -> Result<(), AppError> {
    if key.trim().is_empty() {
        return Err(AppError::InvalidInput {
            reason: format!("rule {rule_id} requires a non-empty companion file key"),
        });
    }

    let path = Path::new(key);
    if path.is_absolute() {
        return Err(AppError::InvalidInput {
            reason: format!("rule {rule_id} companion file key must be relative: `{key}`"),
        });
    }

    let mut normal_component_count = 0usize;
    for component in path.components() {
        match component {
            Component::Normal(_) => {
                normal_component_count = normal_component_count.saturating_add(1);
            }
            Component::CurDir => {
                return Err(AppError::InvalidInput {
                    reason: format!(
                        "rule {rule_id} companion file key must be a single file name: `{key}`"
                    ),
                });
            }
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(AppError::InvalidInput {
                    reason: format!(
                        "rule {rule_id} companion file key cannot escape Dockerfile directory: `{key}`"
                    ),
                });
            }
        }
    }

    if normal_component_count != 1 {
        return Err(AppError::InvalidInput {
            reason: format!(
                "rule {rule_id} companion file key must be a single file name: `{key}`"
            ),
        });
    }

    Ok(())
}

fn service_has_permission_init_sidecar(
    service_name: &str,
    service: &Mapping,
    services: &Mapping,
) -> bool {
    let init_name = format!("{service_name}-init-perms");
    let init_service_exists = services
        .get(YamlValue::String(init_name.clone()))
        .and_then(YamlValue::as_mapping)
        .is_some();
    if !init_service_exists {
        return false;
    }

    let Some(depends_on) = service.get(YamlValue::String("depends_on".to_string())) else {
        return false;
    };

    match depends_on {
        YamlValue::Mapping(map) => map.get(YamlValue::String(init_name.clone())).is_some(),
        YamlValue::Sequence(items) => items
            .iter()
            .filter_map(YamlValue::as_str)
            .any(|item| item == init_name.as_str()),
        _ => false,
    }
}

fn get_service_key<'a>(service: &'a Mapping, key: &str) -> Option<&'a YamlValue> {
    service.get(YamlValue::String(key.to_string()))
}

fn get_service_path<'a>(
    service: &'a Mapping,
    key: &str,
) -> Result<Option<&'a YamlValue>, AppError> {
    if key.contains('.') || key.contains('[') {
        let path = parse_yaml_path(key).map_err(|error| AppError::InvalidInput {
            reason: format!("invalid compose key path `{key}`: {error}"),
        })?;
        Ok(get_mapping_path(service, &path))
    } else {
        Ok(get_service_key(service, key))
    }
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

fn collect_sensitive_env_keys(service: &Mapping) -> Vec<String> {
    let mut keys = BTreeSet::new();
    let Some(environment) = service.get(YamlValue::String("environment".to_string())) else {
        return Vec::new();
    };

    match environment {
        YamlValue::Mapping(map) => {
            for key in map.keys().filter_map(YamlValue::as_str) {
                if is_sensitive_env_key(key) {
                    keys.insert(key.to_string());
                }
            }
        }
        YamlValue::Sequence(items) => {
            for item in items {
                let Some(entry) = item.as_str() else {
                    continue;
                };
                let key = entry.split('=').next().map(str::trim).unwrap_or("");
                if is_sensitive_env_key(key) {
                    keys.insert(key.to_string());
                }
            }
        }
        YamlValue::String(entry) => {
            let key = entry.split('=').next().map(str::trim).unwrap_or("");
            if is_sensitive_env_key(key) {
                keys.insert(key.to_string());
            }
        }
        _ => {}
    }

    keys.into_iter().collect()
}

fn collect_declared_secret_sources(service: &Mapping) -> BTreeSet<String> {
    let mut secrets = BTreeSet::new();
    let Some(service_secrets) = service.get(YamlValue::String("secrets".to_string())) else {
        return secrets;
    };

    let Some(items) = service_secrets.as_sequence() else {
        return secrets;
    };

    for item in items {
        if let Some(secret_name) = yaml_scalar_to_string(item) {
            insert_normalized_secret_name(&mut secrets, &secret_name);
            continue;
        }
        let Some(map) = item.as_mapping() else {
            continue;
        };
        for key in ["source", "target", "name"] {
            let Some(secret_name) = map
                .get(YamlValue::String(key.to_string()))
                .and_then(yaml_scalar_to_string)
            else {
                continue;
            };
            if key == "target" && secret_name.contains('/') {
                continue;
            }
            insert_normalized_secret_name(&mut secrets, &secret_name);
        }
    }

    secrets
}

fn insert_normalized_secret_name(secrets: &mut BTreeSet<String>, secret_name: &str) {
    if secret_name.trim().is_empty() {
        return;
    }
    secrets.insert(secret_name_for_env_key(secret_name));
}

fn is_sensitive_env_key(key: &str) -> bool {
    let normalized = key.trim().to_ascii_uppercase();
    if normalized.is_empty() || normalized.ends_with("_FILE") {
        return false;
    }
    let segments: Vec<&str> = normalized.split('_').collect();
    segments.iter().any(|segment| {
        matches!(
            *segment,
            "TOKEN"
                | "PASS"
                | "PASSWORD"
                | "SECRET"
                | "KEY"
                | "CREDENTIAL"
                | "CREDENTIALS"
                | "CRED"
                | "AUTH"
        )
    }) || normalized.ends_with("TOKEN")
        || normalized.ends_with("PASS")
        || normalized.ends_with("PASSWORD")
        || normalized.ends_with("SECRET")
        || normalized.ends_with("KEY")
        || normalized.ends_with("CREDENTIAL")
        || normalized.ends_with("CREDENTIALS")
        || normalized.ends_with("CRED")
        || normalized.ends_with("AUTH")
}

fn secret_name_for_env_key(key: &str) -> String {
    let mut output = String::new();
    let mut prev_underscore = false;
    for ch in key.to_ascii_lowercase().chars() {
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
    let normalized = output.trim_matches('_').to_string();
    if normalized.is_empty() {
        return "secret".to_string();
    }
    normalized
}

fn has_digest_marker(image: &str) -> bool {
    image.split_once('@').is_some_and(|(_, digest)| {
        digest
            .get(0..7)
            .is_some_and(|prefix| prefix.eq_ignore_ascii_case("sha256:"))
    })
}

fn is_digest_exempt_from_reference(reference: &str) -> bool {
    reference.eq_ignore_ascii_case("scratch")
}

fn has_valid_digest_pin(image: &str) -> bool {
    image
        .split_once('@')
        .is_some_and(|(_, digest)| is_valid_sha256_digest(digest))
}

fn is_valid_sha256_digest(digest: &str) -> bool {
    let Some((algorithm, hex)) = digest.split_once(':') else {
        return false;
    };
    algorithm.eq_ignore_ascii_case("sha256")
        && hex.len() == 64
        && hex.bytes().all(|ch| ch.is_ascii_hexdigit())
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

    let mut exact_candidates: BTreeMap<String, String> = BTreeMap::new();
    let mut base_candidates: BTreeMap<String, String> = BTreeMap::new();
    for profile in &cache.profiles {
        let Ok(normalized_profile) = normalize_image_reference(&profile.image) else {
            continue;
        };
        let profile_base = normalized_profile
            .split_once('@')
            .map(|(head, _)| head)
            .unwrap_or(normalized_profile.as_str());
        let Some(digest) = &profile.digest else {
            continue;
        };
        if !is_valid_sha256_digest(digest) {
            continue;
        }
        if normalized_profile == normalized {
            exact_candidates.insert(profile.id.clone(), digest.clone());
            continue;
        }
        if normalized_base == profile_base {
            base_candidates.insert(profile.id.clone(), digest.clone());
        }
    }
    exact_candidates
        .into_values()
        .next()
        .or_else(|| base_candidates.into_values().next())
}

fn lookup_runtime_user_for_image(cache: &CachedProfiles, image: &str) -> Option<String> {
    let normalized = normalize_image_reference(image).ok()?;
    let normalized_base = normalized
        .split_once('@')
        .map(|(head, _)| head)
        .unwrap_or(normalized.as_str());

    let mut exact_candidates: BTreeMap<String, String> = BTreeMap::new();
    let mut base_candidates: BTreeMap<String, String> = BTreeMap::new();
    for profile in &cache.profiles {
        let Ok(normalized_profile) = normalize_image_reference(&profile.image) else {
            continue;
        };
        let profile_base = normalized_profile
            .split_once('@')
            .map(|(head, _)| head)
            .unwrap_or(normalized_profile.as_str());
        let Some(user) = &profile.runtime.user else {
            continue;
        };
        if normalized_profile == normalized {
            exact_candidates.insert(profile.id.clone(), user.clone());
            continue;
        }
        if normalized_base == profile_base {
            base_candidates.insert(profile.id.clone(), user.clone());
        }
    }
    exact_candidates
        .into_values()
        .next()
        .or_else(|| base_candidates.into_values().next())
}

fn lookup_profile_for_service<'a>(
    cache: &'a CachedProfiles,
    service: &Mapping,
) -> Option<&'a ImageProfile> {
    let image = service
        .get(YamlValue::String("image".to_string()))
        .and_then(yaml_scalar_to_string)?;
    let normalized = normalize_image_reference(&image).ok()?;
    let normalized_base = normalized
        .split_once('@')
        .map(|(head, _)| head)
        .unwrap_or(normalized.as_str());

    let mut exact_candidates: BTreeMap<String, &ImageProfile> = BTreeMap::new();
    let mut base_candidates: BTreeMap<String, &ImageProfile> = BTreeMap::new();
    for profile in &cache.profiles {
        let Ok(normalized_profile) = normalize_image_reference(&profile.image) else {
            continue;
        };
        let profile_base = normalized_profile
            .split_once('@')
            .map(|(head, _)| head)
            .unwrap_or(normalized_profile.as_str());
        if normalized_profile == normalized {
            exact_candidates.insert(profile.id.clone(), profile);
            continue;
        }
        if normalized_base == profile_base {
            base_candidates.insert(profile.id.clone(), profile);
        }
    }
    exact_candidates
        .into_values()
        .next()
        .or_else(|| base_candidates.into_values().next())
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

fn parse_from_reference(arguments: &str) -> Option<String> {
    let tokens = split_quoted_tokens(arguments);
    if tokens.is_empty() {
        return None;
    }
    let mut index = 0usize;
    while let Some(token) = tokens.get(index) {
        if !token.starts_with("--") {
            break;
        }
        index += 1;
        if !token.contains('=')
            && tokens
                .get(index)
                .is_some_and(|next| !next.starts_with("--"))
        {
            index += 1;
        }
    }
    tokens.get(index).cloned()
}

fn parse_arg_name(arguments: &str) -> Option<String> {
    let token = split_quoted_tokens(arguments).into_iter().next()?;
    let name = token.split('=').next().map(str::trim).unwrap_or("");
    if name.is_empty() {
        return None;
    }
    Some(trim_quotes(name).to_string())
}

fn pin_from_instruction_arguments(arguments: &str, digest: Option<&str>) -> Option<String> {
    let mut tokens = split_quoted_tokens(arguments);
    if tokens.is_empty() {
        return None;
    }
    let mut index = 0usize;
    while let Some(token) = tokens.get(index) {
        if !token.starts_with("--") {
            break;
        }
        index += 1;
        if !token.contains('=')
            && tokens
                .get(index)
                .is_some_and(|next| !next.starts_with("--"))
        {
            index += 1;
        }
    }
    let reference = tokens.get(index)?.to_string();
    if has_valid_digest_pin(&reference) {
        return None;
    }
    tokens[index] = match digest {
        Some(value) => pin_image_with_digest(&reference, value),
        None => pin_image_with_digest(&reference, "sha256:<resolve-required>"),
    };
    Some(format!("FROM {}", tokens.join(" ")))
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

fn has_suid_sgid_strip_in_final_stage(parsed: &ParsedDockerfile) -> bool {
    parsed
        .final_stage_instructions_by_keyword("RUN")
        .iter()
        .any(|instruction| {
            let lower = instruction.arguments.to_ascii_lowercase();
            let has_suid_sgid_selector = lower.contains("-perm /6000")
                || (lower.contains("-perm -4000") && lower.contains("-perm -2000"));
            lower.contains("find /")
                && has_suid_sgid_selector
                && (lower.contains("chmod a-s") || lower.contains("chmod ug-s"))
        })
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
    if service_name.is_empty() || key.is_empty() {
        return None;
    }
    Some((service_name, key))
}

fn parse_compose_service_root_path(path: &str) -> Option<&str> {
    if !path.starts_with("services.") {
        return None;
    }
    let remainder = path.trim_start_matches("services.");
    if remainder.is_empty() || remainder.contains('.') {
        return None;
    }
    Some(remainder)
}

fn parse_depends_on_service_path(path: &str) -> Option<(&str, &str)> {
    if !path.starts_with("services.") {
        return None;
    }
    let remainder = path.trim_start_matches("services.");
    let (service_name, tail) = remainder.split_once('.')?;
    let dependency = tail.strip_prefix("depends_on.")?;
    if service_name.is_empty() || dependency.is_empty() {
        return None;
    }
    Some((service_name, dependency))
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum PathSegment {
    Key(String),
    Index(usize),
}

fn parse_yaml_path(path: &str) -> Result<Vec<PathSegment>, AppError> {
    if path.trim().is_empty() {
        return Err(AppError::InvalidInput {
            reason: "yaml path is empty".to_string(),
        });
    }
    let mut segments = Vec::new();
    for part in path.split('.') {
        if part.is_empty() {
            return Err(AppError::InvalidInput {
                reason: format!("invalid yaml path segment in `{path}`"),
            });
        }
        let mut rest = part;
        loop {
            let Some(open) = rest.find('[') else {
                if !rest.is_empty() {
                    segments.push(PathSegment::Key(rest.to_string()));
                    if segments.len() > MAX_YAML_PATH_SEGMENTS {
                        return Err(AppError::InvalidInput {
                            reason: format!(
                                "yaml path has {} segments; max supported is {MAX_YAML_PATH_SEGMENTS}",
                                segments.len()
                            ),
                        });
                    }
                }
                break;
            };
            let key = &rest[..open];
            if !key.is_empty() {
                segments.push(PathSegment::Key(key.to_string()));
                if segments.len() > MAX_YAML_PATH_SEGMENTS {
                    return Err(AppError::InvalidInput {
                        reason: format!(
                            "yaml path has {} segments; max supported is {MAX_YAML_PATH_SEGMENTS}",
                            segments.len()
                        ),
                    });
                }
            }
            let after_open = &rest[open + 1..];
            let Some(close_rel) = after_open.find(']') else {
                return Err(AppError::InvalidInput {
                    reason: format!("invalid yaml path index in `{path}`"),
                });
            };
            let index_text = &after_open[..close_rel];
            let index = index_text
                .parse::<usize>()
                .map_err(|_| AppError::InvalidInput {
                    reason: format!("invalid yaml path index `{index_text}` in `{path}`"),
                })?;
            if index > MAX_YAML_PATH_INDEX {
                return Err(AppError::InvalidInput {
                    reason: format!(
                        "yaml path index `{index}` exceeds max supported value {MAX_YAML_PATH_INDEX}"
                    ),
                });
            }
            segments.push(PathSegment::Index(index));
            if segments.len() > MAX_YAML_PATH_SEGMENTS {
                return Err(AppError::InvalidInput {
                    reason: format!(
                        "yaml path has {} segments; max supported is {MAX_YAML_PATH_SEGMENTS}",
                        segments.len()
                    ),
                });
            }
            rest = &after_open[close_rel + 1..];
            if rest.is_empty() {
                break;
            }
        }
    }
    Ok(segments)
}

fn get_yaml_path<'a>(value: &'a YamlValue, path: &[PathSegment]) -> Option<&'a YamlValue> {
    let mut current = value;
    for segment in path {
        match segment {
            PathSegment::Key(key) => {
                let mapping = current.as_mapping()?;
                current = mapping.get(YamlValue::String(key.clone()))?;
            }
            PathSegment::Index(index) => {
                let items = current.as_sequence()?;
                current = items.get(*index)?;
            }
        }
    }
    Some(current)
}

fn get_mapping_path<'a>(mapping: &'a Mapping, path: &[PathSegment]) -> Option<&'a YamlValue> {
    let (head, tail) = path.split_first()?;
    match head {
        PathSegment::Key(key) => {
            let value = mapping.get(YamlValue::String(key.clone()))?;
            get_yaml_path(value, tail)
        }
        PathSegment::Index(_) => None,
    }
}

fn set_yaml_value(
    value: &mut YamlValue,
    path: &[PathSegment],
    replacement: YamlValue,
) -> Result<(), AppError> {
    if path.is_empty() {
        *value = replacement;
        return Ok(());
    }

    let mut current = value;
    for segment in &path[..path.len() - 1] {
        current = descend_path_mut(current, segment, true)?;
    }
    let tail = &path[path.len() - 1];
    match tail {
        PathSegment::Key(key) => {
            let mapping = ensure_mapping_mut(current)?;
            mapping.insert(YamlValue::String(key.clone()), replacement);
        }
        PathSegment::Index(index) => {
            let sequence = ensure_sequence_mut(current)?;
            if sequence.len() <= *index {
                sequence.resize(*index + 1, YamlValue::Null);
            }
            sequence[*index] = replacement;
        }
    }
    Ok(())
}

fn list_add_yaml_value(
    value: &mut YamlValue,
    path: &[PathSegment],
    addition: YamlValue,
    debug_path: &str,
) -> Result<(), AppError> {
    if path.is_empty() {
        return Err(AppError::InvalidInput {
            reason: format!("list_add target path is empty at {debug_path}"),
        });
    }

    let mut current = value;
    for segment in &path[..path.len() - 1] {
        current = descend_path_mut(current, segment, true)?;
    }

    let tail = &path[path.len() - 1];
    let target = match tail {
        PathSegment::Key(key) => {
            let mapping = ensure_mapping_mut(current)?;
            mapping
                .entry(YamlValue::String(key.clone()))
                .or_insert_with(|| YamlValue::Sequence(Vec::new()))
        }
        PathSegment::Index(index) => {
            let sequence = ensure_sequence_mut(current)?;
            if sequence.len() <= *index {
                sequence.resize(*index + 1, YamlValue::Sequence(Vec::new()));
            }
            &mut sequence[*index]
        }
    };

    match target {
        YamlValue::Sequence(items) => {
            if !items.iter().any(|entry| entry == &addition) {
                items.push(addition);
            }
        }
        YamlValue::String(existing) => {
            let current_value = YamlValue::String(existing.clone());
            if current_value != addition {
                *target = YamlValue::Sequence(vec![current_value, addition]);
            }
        }
        _ => {
            return Err(AppError::InvalidInput {
                reason: format!("list_add target is not list/string at {debug_path}"),
            });
        }
    }
    Ok(())
}

fn depends_on_add_yaml_value(
    service: &mut YamlValue,
    dependency: &str,
    condition: YamlValue,
) -> Result<(), AppError> {
    let service_mapping = ensure_mapping_mut(service)?;
    let depends_on_key = YamlValue::String("depends_on".to_string());
    let depends_on = service_mapping
        .entry(depends_on_key)
        .or_insert_with(|| YamlValue::Mapping(Mapping::new()));

    if let YamlValue::Sequence(sequence) = depends_on {
        let mut converted = Mapping::new();
        for entry in sequence.iter() {
            if let Some(name) = yaml_scalar_to_string(entry) {
                converted.insert(
                    YamlValue::String(name),
                    serde_yaml::to_value(JsonValue::Bool(true)).map_err(|error| {
                        AppError::InvalidInput {
                            reason: format!(
                                "failed to convert depends_on sequence to mapping value: {error}"
                            ),
                        }
                    })?,
                );
            }
        }
        *depends_on = YamlValue::Mapping(converted);
    }

    let mapping = ensure_mapping_mut(depends_on)?;
    mapping.insert(YamlValue::String(dependency.to_string()), condition);
    Ok(())
}

fn remove_yaml_value(value: &mut YamlValue, path: &[PathSegment]) -> Result<(), AppError> {
    if path.is_empty() {
        return Ok(());
    }

    let mut current = value;
    for segment in &path[..path.len() - 1] {
        current = match descend_path_mut(current, segment, false) {
            Ok(next) => next,
            Err(_) => return Ok(()),
        };
    }
    let tail = &path[path.len() - 1];
    match tail {
        PathSegment::Key(key) => {
            if let Some(mapping) = current.as_mapping_mut() {
                let _ = mapping.remove(YamlValue::String(key.clone()));
            }
        }
        PathSegment::Index(index) => {
            if let Some(sequence) = current.as_sequence_mut() {
                if *index < sequence.len() {
                    let _ = sequence.remove(*index);
                }
            }
        }
    }
    Ok(())
}

fn descend_path_mut<'a>(
    current: &'a mut YamlValue,
    segment: &PathSegment,
    create: bool,
) -> Result<&'a mut YamlValue, AppError> {
    match segment {
        PathSegment::Key(key) => {
            if !current.is_mapping() {
                if !create {
                    return Err(AppError::InvalidInput {
                        reason: "expected mapping while walking yaml path".to_string(),
                    });
                }
                *current = YamlValue::Mapping(Mapping::new());
            }
            let mapping = current
                .as_mapping_mut()
                .ok_or_else(|| AppError::InvalidInput {
                    reason: "failed to access mapping while walking yaml path".to_string(),
                })?;
            Ok(mapping
                .entry(YamlValue::String(key.clone()))
                .or_insert(YamlValue::Null))
        }
        PathSegment::Index(index) => {
            if !current.is_sequence() {
                if !create {
                    return Err(AppError::InvalidInput {
                        reason: "expected sequence while walking yaml path".to_string(),
                    });
                }
                *current = YamlValue::Sequence(Vec::new());
            }
            let sequence = current
                .as_sequence_mut()
                .ok_or_else(|| AppError::InvalidInput {
                    reason: "failed to access sequence while walking yaml path".to_string(),
                })?;
            if sequence.len() <= *index {
                if !create {
                    return Err(AppError::InvalidInput {
                        reason: "sequence index out of bounds while walking yaml path".to_string(),
                    });
                }
                sequence.resize(*index + 1, YamlValue::Null);
            }
            Ok(&mut sequence[*index])
        }
    }
}

fn ensure_mapping_mut(value: &mut YamlValue) -> Result<&mut Mapping, AppError> {
    if !value.is_mapping() {
        *value = YamlValue::Mapping(Mapping::new());
    }
    value
        .as_mapping_mut()
        .ok_or_else(|| AppError::InvalidInput {
            reason: "failed to create mapping".to_string(),
        })
}

fn ensure_sequence_mut(value: &mut YamlValue) -> Result<&mut Vec<YamlValue>, AppError> {
    if !value.is_sequence() {
        *value = YamlValue::Sequence(Vec::new());
    }
    value
        .as_sequence_mut()
        .ok_or_else(|| AppError::InvalidInput {
            reason: "failed to create sequence".to_string(),
        })
}

#[cfg(test)]
mod tests {
    use std::fs;

    use serde_json::json;
    use tempfile::tempdir;

    use super::{
        apply_compose_patch_plan, apply_dockerfile_patch_plan, evaluate_compose_policy,
        evaluate_compose_policy_with_mode, evaluate_dockerfile_policy,
        evaluate_dockerfile_policy_with_cache, evaluate_dockerfile_policy_with_cache_and_source,
        load_policy_pack, parse_policy_pack, PatchOperation, PolicyAction, PolicyDomain,
        PolicyPack, PolicyStrictness, RuleSeverity,
    };
    use crate::error::AppError;
    use crate::heuristics::DeployMode;
    use crate::model::{
        CachedProfiles, ComposeHealthcheckTemplate, ImageProfile, Platform, RuntimeProfile,
    };

    fn base_cache() -> CachedProfiles {
        CachedProfiles {
            schema_version: 3,
            profiles: vec![ImageProfile {
                id: "IMG-1".to_string(),
                image: "docker.io/library/nginx:1.27".to_string(),
                docs_url: None,
                dockerfile_url: None,
                digest: Some(
                    "sha256:1111111111111111111111111111111111111111111111111111111111111111"
                        .to_string(),
                ),
                config_digest: Some(
                    "sha256:2222222222222222222222222222222222222222222222222222222222222222"
                        .to_string(),
                ),
                platforms: vec![Platform {
                    os: "linux".to_string(),
                    arch: "amd64".to_string(),
                }],
                runtime: RuntimeProfile {
                    user: Some("1001:1001".to_string()),
                    ..RuntimeProfile::default()
                },
                sources: Vec::new(),
                notes: Vec::new(),
                researched_config: Default::default(),
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
    fn parse_policy_pack_compiles_build_arg_action() {
        let yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-REPRODUCIBLE
    severity: warn
    action: require_build_arg
    target: dockerfile
    key: SOURCE_DATE_EPOCH
"#;
        let policy = parse_policy_pack(yaml).expect("policy should parse");
        assert!(matches!(
            policy.rules[0].action,
            PolicyAction::RequireBuildArg { .. }
        ));
    }

    #[test]
    fn parse_policy_pack_compiles_healthcheck_and_companion_actions() {
        let yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-HEALTHCHECK
    severity: warn
    action: require_healthcheck
    target: final_stage
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: .dockerignore
"#;
        let policy = parse_policy_pack(yaml).expect("policy should parse");
        assert!(matches!(
            policy.rules[0].action,
            PolicyAction::RequireHealthcheck
        ));
        assert!(matches!(
            policy.rules[1].action,
            PolicyAction::RequireCompanionFile { .. }
        ));
    }

    #[test]
    fn parse_policy_pack_rejects_compose_rule_with_invalid_target() {
        let yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-READONLY
    severity: warn
    action: ensure_key
    target: services.api
    key: read_only
    value: true
"#;
        let result = parse_policy_pack(yaml);
        match result {
            Err(AppError::InvalidInput { reason }) => {
                assert!(reason.contains("unsupported target"));
                assert!(reason.contains("service.*"));
            }
            other => panic!("expected invalid target error, got {other:?}"),
        }
    }

    #[test]
    fn parse_policy_pack_rejects_dockerfile_rule_with_invalid_target() {
        let yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-HEALTHCHECK
    severity: warn
    action: require_healthcheck
    target: dockerfile
"#;
        let result = parse_policy_pack(yaml);
        match result {
            Err(AppError::InvalidInput { reason }) => {
                assert!(reason.contains("unsupported target"));
                assert!(reason.contains("final_stage"));
            }
            other => panic!("expected invalid target error, got {other:?}"),
        }
    }

    #[test]
    fn parse_policy_pack_rejects_action_not_supported_in_domain() {
        let yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-WRONG-ACTION
    severity: warn
    action: ensure_key
    target: dockerfile
    key: read_only
    value: true
"#;
        let result = parse_policy_pack(yaml);
        match result {
            Err(AppError::InvalidInput { reason }) => {
                assert!(reason.contains("not supported"));
            }
            other => panic!("expected unsupported action error, got {other:?}"),
        }
    }

    #[test]
    fn parse_policy_pack_rejects_unsafe_label_key() {
        let yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-OCI-LABELS
    severity: warn
    action: require_labels
    target: final_stage
    labels:
      - "org.opencontainers.image.source\nRUN whoami"
"#;
        let result = parse_policy_pack(yaml);
        match result {
            Err(AppError::InvalidInput { reason }) => {
                assert!(reason.contains("label key"));
            }
            other => panic!("expected invalid label key error, got {other:?}"),
        }
    }

    #[test]
    fn parse_policy_pack_rejects_unsafe_build_arg_key() {
        let yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-REPRODUCIBLE
    severity: warn
    action: require_build_arg
    target: dockerfile
    key: SOURCE DATE
"#;
        let result = parse_policy_pack(yaml);
        match result {
            Err(AppError::InvalidInput { reason }) => {
                assert!(reason.contains("build arg key"));
            }
            other => panic!("expected invalid build arg key error, got {other:?}"),
        }
    }

    #[test]
    fn parse_policy_pack_accepts_repo_dockerfile_policy_files() {
        let balanced = include_str!("../../../../references/policy-dockerfile-balanced.yaml");
        let enforcing = include_str!("../../../../references/policy-dockerfile-enforcing.yaml");
        let balanced_policy = parse_policy_pack(balanced).expect("balanced policy should parse");
        let enforcing_policy = parse_policy_pack(enforcing).expect("enforcing policy should parse");
        assert_eq!(balanced_policy.domain, PolicyDomain::Dockerfile);
        assert_eq!(enforcing_policy.domain, PolicyDomain::Dockerfile);
    }

    #[test]
    fn load_policy_pack_rejects_oversized_file() {
        let temp = tempdir().expect("temp dir should be created");
        let policy_path = temp.path().join("policy.yaml");
        let file = fs::File::create(&policy_path).expect("policy file should be created");
        file.set_len(1_048_577)
            .expect("policy file should be sized");

        let result = load_policy_pack(&policy_path, PolicyDomain::Compose);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
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
    fn evaluate_dockerfile_policy_rejects_invalid_target_in_manual_policy_pack() {
        let policy = PolicyPack {
            version: 1,
            domain: PolicyDomain::Dockerfile,
            strictness: PolicyStrictness::Balanced,
            rules: vec![super::PolicyRule {
                id: "AC-DF-HEALTHCHECK".to_string(),
                severity: RuleSeverity::Warn,
                action: PolicyAction::RequireHealthcheck,
                target: "dockerfile".to_string(),
                rationale: "invalid target for this action".to_string(),
            }],
        };
        let result = evaluate_dockerfile_policy("FROM alpine:3.20", &policy);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
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
    fn apply_dockerfile_patch_plan_applies_header_replace_and_final_stage_insertions() {
        let dockerfile = r#"FROM docker.io/library/debian:12-slim
RUN apt-get update && apt-get install -y curl
USER root
"#;
        let plan = vec![
            PatchOperation {
                op: "insert_after".to_string(),
                path: "dockerfile.header".to_string(),
                value: json!("ARG SOURCE_DATE_EPOCH"),
                rule_id: "AC-DF-REPRODUCIBLE".to_string(),
            },
            PatchOperation {
                op: "replace_instruction".to_string(),
                path: "dockerfile.FROM.line:1".to_string(),
                value: json!(
                    "FROM docker.io/library/debian:12-slim@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                ),
                rule_id: "AC-DF-FROM-DIGEST".to_string(),
            },
            PatchOperation {
                op: "replace_instruction".to_string(),
                path: "dockerfile.final_stage.USER".to_string(),
                value: json!("USER 65532:65532"),
                rule_id: "AC-DF-USER".to_string(),
            },
            PatchOperation {
                op: "insert_after".to_string(),
                path: "dockerfile.final_stage.last_run_or_from".to_string(),
                value: json!(
                    "RUN find / -xdev -type f \\( -perm -4000 -o -perm -2000 \\) -exec chmod a-s {} +"
                ),
                rule_id: "AC-DF-SUID-SGID".to_string(),
            },
        ];

        let patched = apply_dockerfile_patch_plan(dockerfile, &plan).expect("patch apply works");
        assert!(patched.contains("ARG SOURCE_DATE_EPOCH"));
        assert!(patched
            .contains("@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"));
        assert!(patched.contains("USER 65532:65532"));
        assert!(patched.contains(
            "RUN find / -xdev -type f \\( -perm -4000 -o -perm -2000 \\) -exec chmod a-s {} +"
        ));
    }

    #[test]
    fn apply_dockerfile_patch_plan_rejects_unknown_sentinel_path() {
        let dockerfile = "FROM docker.io/library/debian:12-slim\n";
        let plan = vec![PatchOperation {
            op: "insert_after".to_string(),
            path: "dockerfile.final_stage.unsupported_anchor".to_string(),
            value: json!("HEALTHCHECK CMD [\"true\"]"),
            rule_id: "AC-DF-HEALTHCHECK".to_string(),
        }];
        let result = apply_dockerfile_patch_plan(dockerfile, &plan);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn apply_dockerfile_patch_plan_inserts_header_after_leading_comment_preamble() {
        let dockerfile = r#"# syntax=docker/dockerfile:1.7
# check=error=true

FROM docker.io/library/debian:12-slim
"#;
        let plan = vec![PatchOperation {
            op: "insert_after".to_string(),
            path: "dockerfile.header".to_string(),
            value: json!("ARG SOURCE_DATE_EPOCH"),
            rule_id: "AC-DF-REPRODUCIBLE".to_string(),
        }];

        let patched = apply_dockerfile_patch_plan(dockerfile, &plan).expect("patch apply works");
        let lines: Vec<&str> = patched.lines().collect();
        assert_eq!(lines[0], "# syntax=docker/dockerfile:1.7");
        assert_eq!(lines[1], "# check=error=true");
        assert_eq!(lines[2], "");
        assert_eq!(lines[3], "ARG SOURCE_DATE_EPOCH");
        assert_eq!(lines[4], "FROM docker.io/library/debian:12-slim");
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

        let patched = apply_compose_patch_plan(compose, &plan, DeployMode::Compose)
            .expect("patch apply should work");
        assert!(patched.contains("read_only: true"));
        assert!(patched.contains("security_opt:"));
        assert!(patched.contains("no-new-privileges:true"));
    }

    #[test]
    fn apply_compose_patch_plan_noop_preserves_bytes() {
        let compose = "services:\n  web:\n    image: nginx:1.27\n";
        let patched = apply_compose_patch_plan(compose, &[], DeployMode::Compose)
            .expect("empty patch plan should preserve");
        assert_eq!(patched, compose);
    }

    #[test]
    fn evaluate_compose_policy_forbid_key_removes_forbidden_setting() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
    privileged: true
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-PRIVILEGED
    severity: warn
    action: forbid_key
    target: service.*
    key: privileged
"#;

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert_eq!(result.violations.len(), 1);
        assert_eq!(result.patch_plan.len(), 1);
        assert_eq!(result.patch_plan[0].op, "remove");
        assert_eq!(result.patch_plan[0].path, "services.web.privileged");
    }

    #[test]
    fn apply_compose_patch_plan_supports_remove() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
    privileged: true
"#;
        let plan = vec![PatchOperation {
            op: "remove".to_string(),
            path: "services.web.privileged".to_string(),
            value: json!(null),
            rule_id: "AC-CMP-PRIVILEGED".to_string(),
        }];

        let patched = apply_compose_patch_plan(compose, &plan, DeployMode::Compose)
            .expect("patch apply should work");
        assert!(!patched.contains("privileged: true"));
    }

    #[test]
    fn evaluate_compose_policy_supports_nested_key_targets() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
    logging:
      options:
        max-size: "5m"
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-LOGSIZE
    severity: warn
    action: ensure_key
    target: service.*
    key: logging.options.max-size
    value: "10m"
"#;

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert_eq!(result.violations.len(), 1);
        assert_eq!(
            result.patch_plan.first().map(|patch| patch.path.as_str()),
            Some("services.web.logging.options.max-size")
        );
    }

    #[test]
    fn evaluate_compose_policy_rejects_invalid_key_path() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-BADKEY
    severity: warn
    action: ensure_key
    target: service.*
    key: healthcheck[
    value: true
"#;

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_compose_policy(compose, &base_cache(), &policy);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn evaluate_compose_policy_resolves_merge_key_inherited_values() {
        let compose = r#"
x-hardening-core: &hardening_core
  cap_drop:
    - ALL
  read_only: true
  security_opt:
    - no-new-privileges:true
services:
  web:
    <<: *hardening_core
    image: nginx:1.27
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-READONLY
    severity: warn
    action: ensure_key
    target: service.*
    key: read_only
    value: true
  - id: AC-CMP-CAPDROP
    severity: warn
    action: ensure_list_contains
    target: service.*
    key: cap_drop
    value: ALL
  - id: AC-CMP-NNP
    severity: warn
    action: ensure_list_contains
    target: service.*
    key: security_opt
    value: no-new-privileges:true
"#;

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_resolves_nested_merge_key_values() {
        let compose = r#"
x-healthcheck-defaults: &healthcheck_defaults
  interval: 30s
  timeout: 5s
services:
  web:
    image: nginx:1.27
    healthcheck:
      <<: *healthcheck_defaults
      test:
        - CMD-SHELL
        - curl -f http://localhost:8080/health || exit 1
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-HC-INTERVAL
    severity: warn
    action: ensure_key
    target: service.*
    key: healthcheck.interval
    value: 30s
"#;

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_rejects_invalid_merge_key_source() {
        let compose = r#"
services:
  web:
    <<: true
    image: nginx:1.27
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-READONLY
    severity: warn
    action: ensure_key
    target: service.*
    key: read_only
    value: true
"#;

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_compose_policy(compose, &base_cache(), &policy);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn apply_compose_patch_plan_supports_nested_paths_and_indexes() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
"#;
        let plan = vec![
            PatchOperation {
                op: "set".to_string(),
                path: "services.web.logging.options.max-size".to_string(),
                value: json!("10m"),
                rule_id: "AC-CMP-LOGSIZE".to_string(),
            },
            PatchOperation {
                op: "set".to_string(),
                path: "services.web.healthcheck.test[0]".to_string(),
                value: json!("CMD"),
                rule_id: "AC-CMP-HC".to_string(),
            },
        ];

        let patched = apply_compose_patch_plan(compose, &plan, DeployMode::Compose)
            .expect("patch apply should work");
        assert!(patched.contains("logging:"));
        assert!(patched.contains("max-size:"));
        assert!(patched.contains("10m"));
        assert!(patched.contains("healthcheck:"));
        assert!(patched.contains("- CMD"));
    }

    #[test]
    fn evaluate_compose_policy_supports_heuristic_actions() {
        let compose = r#"
services:
  db:
    image: postgres:16.4-alpine
    user: "999:999"
    volumes:
      - pgdata:/var/lib/postgresql/data
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-PERMS-INIT
    severity: warn
    action: ensure_volume_permissions
    target: service.*
  - id: AC-CMP-HEALTH
    severity: warn
    action: synthesize_healthcheck
    target: service.*
  - id: AC-CMP-RESOURCES
    severity: warn
    action: ensure_resource_limits
    target: service.*
    mode: compose
"#;
        let mut cache = base_cache();
        cache.profiles[0].image = "docker.io/library/postgres:16.4-alpine".to_string();
        cache.profiles[0].runtime.user = Some("999:999".to_string());
        cache.profiles[0].runtime.exposed_ports = vec!["5432/tcp".to_string()];
        cache.profiles[0]
            .runtime
            .tools
            .insert("pg_isready".to_string(), true);
        cache.profiles[0]
            .researched_config
            .preferred_healthcheck = Some(ComposeHealthcheckTemplate {
            test: vec![
                "CMD-SHELL".to_string(),
                "pg_isready -U \"$${POSTGRES_USER:-postgres}\" -d \"$${POSTGRES_DB:-postgres}\" || exit 1"
                    .to_string(),
            ],
            interval: Some("10s".to_string()),
            timeout: Some("5s".to_string()),
            start_period: Some("20s".to_string()),
            retries: Some(10),
        });

        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &cache, &policy).expect("evaluation should work");
        assert!(result
            .patch_plan
            .iter()
            .any(|patch| patch.op == "inject_service" && patch.path == "services.db-init-perms"));
        assert!(result.patch_plan.iter().any(|patch| {
            patch.op == "depends_on_add" && patch.path == "services.db.depends_on.db-init-perms"
        }));
        assert!(result
            .patch_plan
            .iter()
            .any(|patch| patch.path == "services.db.healthcheck"));
    }

    #[test]
    fn apply_compose_patch_plan_supports_inject_service_and_depends_on_add() {
        let compose = r#"
services:
  db:
    image: postgres:16.4-alpine
"#;
        let plan = vec![
            PatchOperation {
                op: "inject_service".to_string(),
                path: "services.db-init-perms".to_string(),
                value: json!({
                    "image": "docker.io/library/alpine:3.20",
                    "command": ["/bin/sh", "-c", "true"]
                }),
                rule_id: "AC-CMP-PERMS-INIT".to_string(),
            },
            PatchOperation {
                op: "depends_on_add".to_string(),
                path: "services.db.depends_on.db-init-perms".to_string(),
                value: json!({"condition": "service_completed_successfully"}),
                rule_id: "AC-CMP-PERMS-INIT".to_string(),
            },
        ];
        let patched = apply_compose_patch_plan(compose, &plan, DeployMode::Compose)
            .expect("patch apply should work");
        assert!(patched.contains("db-init-perms:"));
        assert!(patched.contains("depends_on:"));
        assert!(patched.contains("service_completed_successfully"));
    }

    #[test]
    fn apply_compose_patch_plan_supports_set_root_for_volume_declarations() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
"#;
        let plan = vec![PatchOperation {
            op: "set_root".to_string(),
            path: "volumes.api_cache".to_string(),
            value: json!({}),
            rule_id: "AC-CMP-WRITABLE".to_string(),
        }];
        let patched = apply_compose_patch_plan(compose, &plan, DeployMode::Compose)
            .expect("patch apply should work");
        assert!(patched.contains("volumes:"));
        assert!(patched.contains("api_cache: {}"));
    }

    #[test]
    fn evaluate_compose_policy_flags_sensitive_env_without_secret_reference() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    environment:
      API_TOKEN: insecure-inline-value
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: enforcing
rules:
  - id: AC-CMP-SECRETS
    severity: block
    action: require_sensitive_env_secrets
    target: service.*
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.rule_id == "AC-CMP-SECRETS"));
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_allows_sensitive_env_when_secret_is_declared() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    environment:
      API_TOKEN: ${API_TOKEN}
    secrets:
      - api_token
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-SECRETS
    severity: warn
    action: require_sensitive_env_secrets
    target: service.*
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_allows_sensitive_env_when_secret_target_alias_matches() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    environment:
      API_TOKEN: ${API_TOKEN}
    secrets:
      - source: api-token-v2
        target: api_token
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-SECRETS
    severity: warn
    action: require_sensitive_env_secrets
    target: service.*
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_keeps_violation_for_unrelated_secret_name() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    environment:
      API_TOKEN: ${API_TOKEN}
    secrets:
      - source: database_password
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-SECRETS
    severity: warn
    action: require_sensitive_env_secrets
    target: service.*
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert_eq!(result.violations.len(), 1);
        assert!(result.violations[0].reason.contains("api_token"));
    }

    #[test]
    fn evaluate_compose_policy_flags_credential_and_auth_env_without_matching_secrets() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    environment:
      DB_CREDENTIALS: ${DB_CREDENTIALS}
      REGISTRY_AUTH: ${REGISTRY_AUTH}
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-SECRETS
    severity: warn
    action: require_sensitive_env_secrets
    target: service.*
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert_eq!(result.violations.len(), 2);
        assert!(result
            .violations
            .iter()
            .any(|item| item.reason.contains("db_credentials")));
        assert!(result
            .violations
            .iter()
            .any(|item| item.reason.contains("registry_auth")));
    }

    #[test]
    fn evaluate_compose_policy_allows_credential_and_auth_env_with_matching_secrets() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    environment:
      DB_CREDENTIALS: ${DB_CREDENTIALS}
      REGISTRY_AUTH: ${REGISTRY_AUTH}
    secrets:
      - db_credentials
      - registry_auth
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-SECRETS
    severity: warn
    action: require_sensitive_env_secrets
    target: service.*
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_ensures_writable_paths_for_read_only_services() {
        let compose = r#"
services:
  db:
    image: postgres:16.4-alpine
    read_only: true
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: enforcing
rules:
  - id: AC-CMP-WRITABLE
    severity: block
    action: ensure_writable_paths
    target: service.*
"#;
        let mut cache = base_cache();
        cache.profiles[0].image = "docker.io/library/postgres:16.4-alpine".to_string();
        cache.profiles[0].runtime.volumes = vec!["/var/lib/postgresql/data".to_string()];
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_compose_policy(compose, &cache, &policy).expect("evaluation works");
        assert!(result
            .patch_plan
            .iter()
            .any(|item| item.path == "services.db.tmpfs" && item.op == "list_add"));
        assert!(result.patch_plan.iter().any(|item| {
            item.path == "volumes.db_var_lib_postgresql_data" && item.op == "set_root"
        }));
    }

    #[test]
    fn evaluate_compose_policy_warns_and_skips_init_perms_for_bind_mounts() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    user: "1000:1000"
    volumes:
      - ./host-data:/data
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-PERMS-INIT
    severity: warn
    action: ensure_volume_permissions
    target: service.*
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.reason.contains("disabled by default")));
        assert!(!result
            .patch_plan
            .iter()
            .any(|item| item.op == "inject_service"));
    }

    #[test]
    fn evaluate_compose_policy_skips_init_perms_in_swarm_mode() {
        let compose = r#"
services:
  db:
    image: postgres:16.4-alpine
    user: "999:999"
    volumes:
      - db_data:/var/lib/postgresql/data
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-PERMS-INIT
    severity: warn
    action: ensure_volume_permissions
    target: service.*
"#;
        let mut cache = base_cache();
        cache.profiles[0].image = "docker.io/library/postgres:16.4-alpine".to_string();
        cache.profiles[0].runtime.user = Some("999:999".to_string());
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_compose_policy_with_mode(compose, &cache, &policy, DeployMode::Swarm)
            .expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.reason.contains("skipped in swarm mode")));
        assert!(!result
            .patch_plan
            .iter()
            .any(|item| item.op == "inject_service"));
    }

    #[test]
    fn evaluate_compose_policy_skips_non_root_requirement_for_init_perms_services() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    user: "101:101"
  api-init-perms:
    image: docker.io/library/alpine:3.20@sha256:a4f4213abb84c497377b8544c81b3564f313746700372ec4fe84653e4fb03805
    user: "0:0"
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: enforcing
rules:
  - id: AC-CMP-USER
    severity: block
    action: require_non_root_user
    target: service.*
    key: user
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_skips_reinjecting_existing_init_perms_sidecar() {
        let compose = r#"
services:
  api:
    image: nginx:1.27
    user: "101:101"
    volumes:
      - app_data:/var/cache/app
    depends_on:
      api-init-perms:
        condition: service_completed_successfully
  api-init-perms:
    image: docker.io/library/alpine:3.20@sha256:a4f4213abb84c497377b8544c81b3564f313746700372ec4fe84653e4fb03805
    user: "0:0"
    read_only: true
    cap_drop: [ALL]
    cap_add: [CHOWN, FOWNER]
    security_opt: [no-new-privileges:true]
    network_mode: none
    restart: "no"
    volumes:
      - app_data:/mnt/perm-0
volumes:
  app_data: {}
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-PERMS-INIT
    severity: warn
    action: ensure_volume_permissions
    target: service.*
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(!result
            .patch_plan
            .iter()
            .any(|item| item.op == "inject_service"));
        assert!(!result
            .patch_plan
            .iter()
            .any(|item| item.op == "depends_on_add"));
    }

    #[test]
    fn compose_hardening_patch_plan_is_idempotent_for_writable_path_rules() {
        let compose = r#"
services:
  db:
    image: postgres:16.4-alpine
    read_only: true
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: enforcing
rules:
  - id: AC-CMP-WRITABLE
    severity: block
    action: ensure_writable_paths
    target: service.*
"#;
        let mut cache = base_cache();
        cache.profiles[0].image = "docker.io/library/postgres:16.4-alpine".to_string();
        cache.profiles[0].runtime.volumes = vec!["/var/lib/postgresql/data".to_string()];
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let initial = evaluate_compose_policy(compose, &cache, &policy).expect("evaluation works");
        let hardened_once =
            apply_compose_patch_plan(compose, &initial.patch_plan, DeployMode::Compose)
                .expect("first patch apply works");
        let hardened_twice =
            apply_compose_patch_plan(&hardened_once, &initial.patch_plan, DeployMode::Compose)
                .expect("second patch apply works");
        assert_eq!(hardened_once, hardened_twice);

        let reevaluated =
            evaluate_compose_policy(&hardened_once, &cache, &policy).expect("reeval works");
        assert!(reevaluated.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_dockerfile_policy_reports_unpinned_from_references() {
        let dockerfile = "FROM docker.io/library/alpine:3.20\nRUN echo hi\n";
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-FROM-DIGEST
    severity: block
    action: require_from_digest
    target: dockerfile
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.rule_id == "AC-DF-FROM-DIGEST"));
    }

    #[test]
    fn evaluate_dockerfile_policy_allows_scratch_from_without_digest() {
        let dockerfile = "FROM scratch\nCMD [\"/app\"]\n";
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-FROM-DIGEST
    severity: block
    action: require_from_digest
    target: dockerfile
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_dockerfile_policy_flags_invalid_from_digest_marker() {
        let dockerfile = "FROM docker.io/library/alpine:3.20@sha256:abc\nRUN echo hi\n";
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-FROM-DIGEST
    severity: block
    action: require_from_digest
    target: dockerfile
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.reason.contains("invalid sha256 digest")));
    }

    #[test]
    fn evaluate_compose_policy_flags_invalid_image_digest_marker() {
        let compose = r#"
services:
  web:
    image: nginx@sha256:abc
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
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.reason.contains("invalid")));
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_prefers_exact_tag_digest_match_over_base_fallback() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-DIGEST
    severity: warn
    action: require_image_digest
    target: service.*
    key: image
"#;
        let mut cache = base_cache();
        cache.profiles = vec![
            ImageProfile {
                id: "IMG-1".to_string(),
                image: "docker.io/library/nginx:latest".to_string(),
                digest: Some(
                    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                        .to_string(),
                ),
                ..cache.profiles[0].clone()
            },
            ImageProfile {
                id: "IMG-2".to_string(),
                image: "docker.io/library/nginx:1.27".to_string(),
                digest: Some(
                    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                        .to_string(),
                ),
                ..cache.profiles[0].clone()
            },
        ];
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_compose_policy(compose, &cache, &policy).expect("evaluation works");
        let replacement = result
            .patch_plan
            .iter()
            .find(|item| item.path == "services.web.image")
            .and_then(|item| item.value.as_str())
            .expect("image replacement patch should be generated");
        assert!(replacement.starts_with("nginx:1.27@"));
        assert!(replacement
            .contains("sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));
    }

    #[test]
    fn evaluate_dockerfile_policy_uses_cached_digest_for_from_patch() {
        let dockerfile = "FROM docker.io/library/alpine:3.20 AS runtime\nRUN echo hi\n";
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-FROM-DIGEST
    severity: block
    action: require_from_digest
    target: dockerfile
"#;
        let mut cache = base_cache();
        cache.profiles[0].image = "docker.io/library/alpine:3.20".to_string();
        cache.profiles[0].digest = Some(
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".to_string(),
        );
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy_with_cache(dockerfile, &policy, Some(&cache))
            .expect("evaluation works");
        let replacement = result
            .patch_plan
            .iter()
            .find(|item| item.rule_id == "AC-DF-FROM-DIGEST")
            .and_then(|item| item.value.as_str())
            .expect("replacement should exist");
        assert!(replacement.contains(
            "docker.io/library/alpine:3.20@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ));
    }

    #[test]
    fn evaluate_dockerfile_policy_reports_missing_suid_sgid_strip() {
        let dockerfile = r#"
FROM docker.io/library/debian:12
RUN apt-get update
USER 1000:1000
"#;
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-SUID
    severity: block
    action: require_suid_sgid_strip
    target: final_stage
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.rule_id == "AC-DF-SUID"));
        assert!(result.patch_plan.iter().any(|patch| {
            patch.rule_id == "AC-DF-SUID" && patch.path == "dockerfile.final_stage.last_run_or_from"
        }));
        assert!(result
            .patch_plan
            .iter()
            .filter(|patch| patch.rule_id == "AC-DF-SUID")
            .all(|patch| !patch.value.as_str().unwrap_or_default().contains("|| true")));
    }

    #[test]
    fn evaluate_dockerfile_policy_accepts_portable_suid_sgid_strip_command() {
        let dockerfile = r#"
FROM docker.io/library/debian:12
RUN find / -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} +
USER 1000:1000
"#;
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-SUID
    severity: block
    action: require_suid_sgid_strip
    target: final_stage
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(!result
            .violations
            .iter()
            .any(|item| item.rule_id == "AC-DF-SUID"));
        assert!(!result
            .patch_plan
            .iter()
            .any(|item| item.rule_id == "AC-DF-SUID"));
    }

    #[test]
    fn evaluate_dockerfile_policy_reports_missing_required_build_arg() {
        let dockerfile = r#"
FROM docker.io/library/debian:12
RUN echo hi
"#;
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-REPRODUCIBLE
    severity: warn
    action: require_build_arg
    target: dockerfile
    key: SOURCE_DATE_EPOCH
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.target == "dockerfile.ARG.SOURCE_DATE_EPOCH"));
        assert!(result.patch_plan.iter().any(|patch| {
            patch.path == "dockerfile.header"
                && patch.value.as_str() == Some("ARG SOURCE_DATE_EPOCH")
        }));
    }

    #[test]
    fn evaluate_dockerfile_policy_accepts_legacy_ensure_arg_action_alias() {
        let dockerfile = r#"
FROM docker.io/library/debian:12
RUN echo hi
"#;
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-REPRODUCIBLE
    severity: warn
    action: ensure_arg
    target: dockerfile
    key: SOURCE_DATE_EPOCH
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.target == "dockerfile.ARG.SOURCE_DATE_EPOCH"));
        assert!(result.patch_plan.iter().any(|patch| {
            patch.path == "dockerfile.header"
                && patch.value.as_str() == Some("ARG SOURCE_DATE_EPOCH")
        }));
    }

    #[test]
    fn evaluate_dockerfile_policy_accepts_existing_required_build_arg() {
        let dockerfile = r#"
ARG SOURCE_DATE_EPOCH
FROM docker.io/library/debian:12
RUN echo hi
"#;
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-REPRODUCIBLE
    severity: warn
    action: require_build_arg
    target: dockerfile
    key: SOURCE_DATE_EPOCH
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_dockerfile_policy_reports_missing_healthcheck() {
        let dockerfile = r#"
FROM docker.io/library/debian:12
RUN echo hi
"#;
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-HEALTHCHECK
    severity: warn
    action: require_healthcheck
    target: final_stage
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.rule_id == "AC-DF-HEALTHCHECK"));
        assert!(result.patch_plan.iter().any(|patch| {
            patch.rule_id == "AC-DF-HEALTHCHECK"
                && patch.path == "dockerfile.final_stage.last_run_or_from"
        }));
    }

    #[test]
    fn evaluate_dockerfile_policy_enforcing_missing_healthcheck_has_no_placeholder_patch() {
        let dockerfile = r#"
FROM docker.io/library/debian:12
RUN echo hi
"#;
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-HEALTHCHECK
    severity: block
    action: require_healthcheck
    target: final_stage
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy(dockerfile, &policy).expect("evaluation works");
        assert!(result
            .violations
            .iter()
            .any(|item| item.rule_id == "AC-DF-HEALTHCHECK"));
        assert!(!result
            .patch_plan
            .iter()
            .any(|patch| patch.rule_id == "AC-DF-HEALTHCHECK"));
    }

    #[test]
    fn evaluate_dockerfile_policy_reports_missing_companion_file() {
        let temp = tempdir().expect("temp dir should be created");
        let dockerfile_path = temp.path().join("Dockerfile");
        let dockerfile = "FROM docker.io/library/debian:12\n";
        fs::write(&dockerfile_path, dockerfile).expect("dockerfile should be written");
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: .dockerignore
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy_with_cache_and_source(
            dockerfile,
            &policy,
            None,
            Some(dockerfile_path.as_path()),
        )
        .expect("evaluation works");
        assert_eq!(result.violations.len(), 1);
        assert!(result.violations[0]
            .reason
            .contains("missing companion file"));
    }

    #[test]
    fn evaluate_dockerfile_policy_accepts_present_companion_file() {
        let temp = tempdir().expect("temp dir should be created");
        let dockerfile_path = temp.path().join("Dockerfile");
        let dockerignore_path = temp.path().join(".dockerignore");
        let dockerfile = "FROM docker.io/library/debian:12\n";
        fs::write(&dockerfile_path, dockerfile).expect("dockerfile should be written");
        fs::write(&dockerignore_path, "target/\n").expect("dockerignore should be written");
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: .dockerignore
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy_with_cache_and_source(
            dockerfile,
            &policy,
            None,
            Some(dockerfile_path.as_path()),
        )
        .expect("evaluation works");
        assert!(result.violations.is_empty());
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_dockerfile_policy_rejects_nonexistent_companion_source_path() {
        let temp = tempdir().expect("temp dir should be created");
        let missing_path = temp.path().join("missing.Dockerfile");
        let dockerfile = "FROM docker.io/library/debian:12\n";
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: .dockerignore
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result = evaluate_dockerfile_policy_with_cache_and_source(
            dockerfile,
            &policy,
            None,
            Some(missing_path.as_path()),
        );
        assert!(
            matches!(
                result,
                Err(AppError::InvalidInput { ref reason })
                    if reason.contains("failed to canonicalize Dockerfile source path")
            ),
            "expected canonicalization failure for missing source path, got {result:?}"
        );
    }

    #[test]
    fn evaluate_dockerfile_policy_reports_companion_when_source_path_is_unavailable() {
        let dockerfile = "FROM docker.io/library/debian:12\n";
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: .dockerignore
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_dockerfile_policy_with_cache_and_source(dockerfile, &policy, None, None)
                .expect("evaluation works");
        assert_eq!(result.violations.len(), 1);
        assert!(result.violations[0]
            .reason
            .contains("without a Dockerfile source path"));
    }

    #[test]
    fn evaluate_dockerfile_policy_enforcing_mode_suppresses_companion_patch_without_source_path() {
        let dockerfile = "FROM docker.io/library/debian:12\n";
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: enforcing
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: block
    action: require_companion_file
    target: dockerfile
    key: .dockerignore
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_dockerfile_policy_with_cache_and_source(dockerfile, &policy, None, None)
                .expect("evaluation works");

        assert_eq!(result.violations.len(), 1);
        assert_eq!(result.violations[0].rule_id, "AC-DF-DOCKERIGNORE");
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn evaluate_compose_policy_does_not_skip_non_sidecar_init_prefix_service() {
        let compose = r#"
services:
  init-api:
    image: nginx:1.27
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-RESTART
    severity: warn
    action: ensure_key
    target: service.*
    key: restart
    value: unless-stopped
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert_eq!(result.violations.len(), 1);
        assert_eq!(result.patch_plan.len(), 1);
        assert_eq!(result.patch_plan[0].path, "services.init-api.restart");
    }

    #[test]
    fn evaluate_compose_policy_skips_init_perms_sidecar_for_ensure_key() {
        let compose = r#"
services:
  api-init-perms:
    image: alpine:3.20
    restart: no
"#;
        let policy_yaml = r#"
version: 1
domain: compose
strictness: balanced
rules:
  - id: AC-CMP-RESTART
    severity: warn
    action: ensure_key
    target: service.*
    key: restart
    value: unless-stopped
"#;
        let policy = parse_policy_pack(policy_yaml).expect("policy should parse");
        let result =
            evaluate_compose_policy(compose, &base_cache(), &policy).expect("evaluation works");
        assert!(result.violations.is_empty());
        assert!(result.patch_plan.is_empty());
    }

    #[test]
    fn parse_policy_pack_rejects_companion_file_absolute_path() {
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: /etc/passwd
"#;
        let result = parse_policy_pack(policy_yaml);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn parse_policy_pack_rejects_companion_file_parent_traversal() {
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: ../../secret
"#;
        let result = parse_policy_pack(policy_yaml);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn parse_policy_pack_rejects_companion_file_curdir_only_key() {
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: .
"#;
        let result = parse_policy_pack(policy_yaml);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn parse_policy_pack_rejects_companion_file_subdirectory_key() {
        let policy_yaml = r#"
version: 1
domain: dockerfile
strictness: balanced
rules:
  - id: AC-DF-DOCKERIGNORE
    severity: warn
    action: require_companion_file
    target: dockerfile
    key: subdir/.dockerignore
"#;
        let result = parse_policy_pack(policy_yaml);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn apply_compose_patch_plan_rejects_oversized_path_index() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
"#;
        let plan = vec![PatchOperation {
            op: "set".to_string(),
            path: "services.web.tmpfs[5000]".to_string(),
            value: json!("/tmp:rw"),
            rule_id: "AC-CMP-WRITABLE".to_string(),
        }];
        let result = apply_compose_patch_plan(compose, &plan, DeployMode::Compose);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }

    #[test]
    fn apply_compose_patch_plan_rejects_dockerfile_sentinel_paths() {
        let compose = r#"
services:
  web:
    image: nginx:1.27
"#;
        let plan = vec![PatchOperation {
            op: "set".to_string(),
            path: "dockerfile.header".to_string(),
            value: json!("ARG SOURCE_DATE_EPOCH"),
            rule_id: "AC-DF-REPRODUCIBLE".to_string(),
        }];
        let result = apply_compose_patch_plan(compose, &plan, DeployMode::Compose);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }
}
