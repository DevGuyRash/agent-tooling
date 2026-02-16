//! Deterministic compose hardening heuristics derived from image/runtime facts.

use serde_json::{json, Value as JsonValue};
use serde_yaml::{Mapping, Value as YamlValue};

use crate::error::AppError;
use crate::model::{ComposeHealthcheckTemplate, ImageProfile, RuntimeProfile};

const INIT_PERMS_IMAGE: &str = "docker.io/library/alpine:3.20@sha256:a4f4213abb84c497377b8544c81b3564f313746700372ec4fe84653e4fb03805";
const BASELINE_TMPFS_SPECS: [&str; 3] = [
    "/tmp:rw,noexec,nosuid,nodev,size=64m",
    "/run:rw,noexec,nosuid,nodev,size=16m",
    "/var/run:rw,noexec,nosuid,nodev,size=16m",
];

/// Deployment mode used by deterministic resource patching.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeployMode {
    /// Local compose mode.
    Compose,
    /// Swarm mode.
    Swarm,
}

impl DeployMode {
    /// Parse deployment mode from CLI/policy text.
    pub fn parse(value: &str) -> Result<Self, AppError> {
        match value {
            "compose" => Ok(Self::Compose),
            "swarm" => Ok(Self::Swarm),
            _ => Err(AppError::InvalidInput {
                reason: format!("unsupported deploy mode: {value}"),
            }),
        }
    }
}

/// Generic deterministic patch emitted by heuristic synthesis.
#[derive(Debug, Clone, PartialEq)]
pub struct HeuristicPatch {
    /// Patch operation.
    pub op: String,
    /// Patch path.
    pub path: String,
    /// Patch value.
    pub value: JsonValue,
    /// Human-readable deterministic reason.
    pub reason: String,
}

/// Return bind mount targets for a service in deterministic order.
pub fn bind_mount_targets(service: &Mapping) -> Vec<String> {
    let mut targets: Vec<String> = collect_service_volume_targets(service)
        .into_iter()
        .filter(|mount| mount.kind == VolumeMountKind::Bind)
        .map(|mount| mount.target)
        .collect();
    targets.sort();
    targets.dedup();
    targets
}

/// Synthesize a deterministic init sidecar and dependency wiring for writable volumes.
pub fn ensure_volume_permissions(
    service_name: &str,
    service: &Mapping,
    profile: Option<&ImageProfile>,
) -> Result<Vec<HeuristicPatch>, AppError> {
    if service_name.ends_with("-init-perms") || service_name.starts_with("init-") {
        return Ok(Vec::new());
    }

    let Some(user) = service_non_root_user(service, profile) else {
        return Ok(Vec::new());
    };

    let mounts: Vec<VolumeMount> = collect_service_volume_targets(service)
        .into_iter()
        .filter(|mount| {
            mount.kind == VolumeMountKind::NamedVolume && mount.source.as_deref().is_some()
        })
        .collect();
    if mounts.is_empty() {
        return Ok(Vec::new());
    }

    let (uid, gid) = resolve_uid_gid(&user, profile);
    let init_name = format!("{service_name}-init-perms");

    let init_mounts: Vec<String> = mounts
        .iter()
        .enumerate()
        .map(|(index, mount)| {
            format!(
                "{}:/mnt/perm-{index}",
                mount.source.as_deref().unwrap_or_default()
            )
        })
        .collect();
    let init_paths: Vec<String> = mounts
        .iter()
        .enumerate()
        .map(|(index, _)| format!("/mnt/perm-{index}"))
        .collect();
    let path_join = init_paths.join(" ");
    let init_script = format!(
        "set -eu; for path in {path_join}; do mkdir -p \"$path\"; owner=\"$(stat -c '%u:%g' \"$path\" 2>/dev/null || true)\"; if [ \"$owner\" != \"{uid}:{gid}\" ]; then chown -R {uid}:{gid} \"$path\"; fi; done"
    );

    Ok(vec![
        HeuristicPatch {
            op: "inject_service".to_string(),
            path: format!("services.{init_name}"),
            value: json!({
              "image": INIT_PERMS_IMAGE,
              "command": ["/bin/sh", "-euxc", init_script],
              "user": "0:0",
              "read_only": true,
              "tmpfs": ["/tmp:rw,noexec,nosuid,nodev,size=16m"],
              "cap_drop": ["ALL"],
              "cap_add": ["CHOWN", "FOWNER"],
              "security_opt": ["no-new-privileges:true"],
              "network_mode": "none",
              "restart": "no",
              "volumes": init_mounts
            }),
            reason: "service runs as non-root with writable volumes; init sidecar enforces deterministic ownership".to_string(),
        },
        HeuristicPatch {
            op: "depends_on_add".to_string(),
            path: format!("services.{service_name}.depends_on.{init_name}"),
            value: json!({ "condition": "service_completed_successfully" }),
            reason: "service startup must wait for permission init sidecar completion".to_string(),
        },
    ])
}

/// Ensure writable paths are present when read-only hardening is applied.
pub fn ensure_writable_paths(
    service_name: &str,
    service: &Mapping,
    profile: Option<&ImageProfile>,
) -> Vec<HeuristicPatch> {
    if service_read_only_disabled(service) {
        return Vec::new();
    }

    let mut patches = Vec::new();
    let existing_mounts = collect_service_volume_targets(service);
    let existing_targets: std::collections::BTreeSet<String> = existing_mounts
        .iter()
        .map(|mount| mount.target.clone())
        .collect();
    let existing_tmpfs_targets = collect_service_tmpfs_targets(service);

    for spec in BASELINE_TMPFS_SPECS {
        let target = spec.split(':').next().unwrap_or(spec);
        if existing_tmpfs_targets.contains(target) || existing_targets.contains(target) {
            continue;
        }
        patches.push(HeuristicPatch {
            op: "list_add".to_string(),
            path: format!("services.{service_name}.tmpfs"),
            value: JsonValue::String(spec.to_string()),
            reason: format!("read-only rootfs requires tmpfs writable runtime path `{target}`"),
        });
    }

    let mut required_persistent_targets = std::collections::BTreeSet::new();
    if let Some(image) = profile {
        for target in &image.researched_config.required_mounts {
            if !target.trim().is_empty() {
                required_persistent_targets.insert(target.trim().to_string());
            }
        }
        for target in &image.runtime.volumes {
            if !target.trim().is_empty() {
                required_persistent_targets.insert(target.trim().to_string());
            }
        }
    }

    for target in required_persistent_targets {
        if BASELINE_TMPFS_SPECS
            .iter()
            .map(|spec| spec.split(':').next().unwrap_or(*spec))
            .any(|item| item == target)
        {
            continue;
        }
        if existing_targets.contains(&target) {
            continue;
        }
        let volume_name = format!("{service_name}_{}", sanitize_volume_target(&target));
        patches.push(HeuristicPatch {
            op: "set_root".to_string(),
            path: format!("volumes.{volume_name}"),
            value: json!({}),
            reason: format!(
                "declaring named volume `{volume_name}` for read-only rootfs writable path `{target}`"
            ),
        });
        patches.push(HeuristicPatch {
            op: "list_add".to_string(),
            path: format!("services.{service_name}.volumes"),
            value: JsonValue::String(format!("{volume_name}:{target}")),
            reason: format!(
                "mounting named volume `{volume_name}` to writable path `{target}` under read-only rootfs"
            ),
        });
    }

    patches
}

/// Synthesize deterministic healthchecks based on image config, curated knowledge, and probe data.
pub fn synthesize_healthcheck(
    service_name: &str,
    service: &Mapping,
    profile: Option<&ImageProfile>,
) -> Vec<HeuristicPatch> {
    if service
        .get(YamlValue::String("healthcheck".to_string()))
        .is_some()
    {
        return Vec::new();
    }

    let distroless = profile
        .map(|image| image.runtime.signatures.distroless)
        .unwrap_or(false);
    let template = [
        profile.and_then(|image| healthcheck_from_runtime(&image.runtime)),
        profile.and_then(|image| image.researched_config.preferred_healthcheck.clone()),
        profile.and_then(healthcheck_from_tools),
    ]
    .into_iter()
    .flatten()
    .find(|candidate| !distroless || !healthcheck_uses_cmd_shell(candidate));

    let Some(healthcheck) = template else {
        return Vec::new();
    };

    vec![HeuristicPatch {
        op: "set".to_string(),
        path: format!("services.{service_name}.healthcheck"),
        value: json!({
          "test": healthcheck.test,
          "interval": healthcheck.interval.unwrap_or_else(|| "10s".to_string()),
          "timeout": healthcheck.timeout.unwrap_or_else(|| "5s".to_string()),
          "start_period": healthcheck.start_period.unwrap_or_else(|| "10s".to_string()),
          "retries": healthcheck.retries.unwrap_or(5)
        }),
        reason: if distroless {
            "healthcheck synthesized from runtime metadata and deterministic knowledge base using distroless-compatible exec form".to_string()
        } else {
            "healthcheck synthesized from runtime metadata and deterministic knowledge base"
                .to_string()
        },
    }]
}

/// Synthesize deterministic capability and device reservations.
pub fn ensure_capability_profile(
    service_name: &str,
    service: &Mapping,
    profile: Option<&ImageProfile>,
) -> Vec<HeuristicPatch> {
    let mut patches = Vec::new();

    if binds_low_port(service, profile.map(|item| &item.runtime)) {
        patches.push(HeuristicPatch {
            op: "list_add".to_string(),
            path: format!("services.{service_name}.cap_add"),
            value: JsonValue::String("NET_BIND_SERVICE".to_string()),
            reason:
                "service binds a privileged port; NET_BIND_SERVICE is required under cap_drop=ALL"
                    .to_string(),
        });
    }

    let Some(image) = profile else {
        return patches;
    };
    if !image.runtime.signatures.gpu_compute {
        return patches;
    }

    let capabilities = if image
        .researched_config
        .preferred_gpu_capabilities
        .is_empty()
    {
        vec!["gpu".to_string(), "compute".to_string()]
    } else {
        image.researched_config.preferred_gpu_capabilities.clone()
    };
    let driver = image
        .researched_config
        .preferred_gpu_driver
        .clone()
        .or_else(|| {
            if image.runtime.signatures.nvidia {
                Some("nvidia".to_string())
            } else {
                None
            }
        });

    let mut device = json!({ "capabilities": capabilities });
    if let Some(driver) = driver {
        device["driver"] = JsonValue::String(driver);
    }

    patches.push(HeuristicPatch {
        op: "set".to_string(),
        path: format!("services.{service_name}.deploy.resources.reservations.devices"),
        value: JsonValue::Array(vec![device]),
        reason:
            "runtime OpenCL/GPU signatures detected; reserving compute devices deterministically"
                .to_string(),
    });

    patches
}

/// Synthesize mode-aware resource limits for compose or swarm workflows.
pub fn ensure_resource_limits(
    service_name: &str,
    service: &Mapping,
    mode: DeployMode,
    memory: &str,
    cpus: &str,
    pids: u64,
) -> Vec<HeuristicPatch> {
    let mut patches = Vec::new();
    match mode {
        DeployMode::Compose => {
            if service
                .get(YamlValue::String("mem_limit".to_string()))
                .is_none()
            {
                patches.push(HeuristicPatch {
                    op: "set".to_string(),
                    path: format!("services.{service_name}.mem_limit"),
                    value: JsonValue::String(memory.to_string()),
                    reason:
                        "compose mode requires explicit mem_limit for deterministic host scheduling"
                            .to_string(),
                });
            }
            if service.get(YamlValue::String("cpus".to_string())).is_none() {
                patches.push(HeuristicPatch {
                    op: "set".to_string(),
                    path: format!("services.{service_name}.cpus"),
                    value: JsonValue::String(cpus.to_string()),
                    reason: "compose mode requires explicit cpus for deterministic host scheduling"
                        .to_string(),
                });
            }
            if service
                .get(YamlValue::String("pids_limit".to_string()))
                .is_none()
            {
                patches.push(HeuristicPatch {
                    op: "set".to_string(),
                    path: format!("services.{service_name}.pids_limit"),
                    value: JsonValue::Number(pids.into()),
                    reason: "compose mode requires explicit pids_limit for process-fork blast-radius control".to_string(),
                });
            }
        }
        DeployMode::Swarm => {
            if !has_key_path(service, "deploy.resources.limits.memory") {
                patches.push(HeuristicPatch {
                    op: "set".to_string(),
                    path: format!("services.{service_name}.deploy.resources.limits.memory"),
                    value: JsonValue::String(memory.to_string()),
                    reason: "swarm mode requires deploy.resources.limits.memory".to_string(),
                });
            }
            if !has_key_path(service, "deploy.resources.limits.cpus") {
                patches.push(HeuristicPatch {
                    op: "set".to_string(),
                    path: format!("services.{service_name}.deploy.resources.limits.cpus"),
                    value: JsonValue::String(cpus.to_string()),
                    reason: "swarm mode requires deploy.resources.limits.cpus".to_string(),
                });
            }
        }
    }
    patches
}

fn service_non_root_user(service: &Mapping, profile: Option<&ImageProfile>) -> Option<String> {
    let configured = service
        .get(YamlValue::String("user".to_string()))
        .and_then(yaml_scalar_to_string);
    if configured
        .as_deref()
        .is_some_and(|value| !is_root_user(value))
    {
        return configured;
    }

    let runtime_user = profile.and_then(|item| item.runtime.user.clone());
    if runtime_user
        .as_deref()
        .is_some_and(|value| !is_root_user(value))
    {
        return runtime_user;
    }

    None
}

fn resolve_uid_gid(user: &str, profile: Option<&ImageProfile>) -> (u32, u32) {
    if let Some((uid, gid)) = parse_uid_gid(user) {
        return (uid, gid);
    }
    let uid = profile
        .and_then(|item| item.researched_config.runtime_uid)
        .unwrap_or(65532);
    let gid = profile
        .and_then(|item| item.researched_config.runtime_gid)
        .unwrap_or(uid);
    (uid, gid)
}

fn parse_uid_gid(value: &str) -> Option<(u32, u32)> {
    if let Some((uid_text, gid_text)) = value.split_once(':') {
        let uid = uid_text.trim().parse::<u32>().ok()?;
        let gid = gid_text.trim().parse::<u32>().ok()?;
        return Some((uid, gid));
    }

    let uid = value.trim().parse::<u32>().ok()?;
    Some((uid, uid))
}

fn collect_service_volume_targets(service: &Mapping) -> Vec<VolumeMount> {
    let Some(value) = service.get(YamlValue::String("volumes".to_string())) else {
        return Vec::new();
    };

    let mut mounts = Vec::new();
    let Some(items) = value.as_sequence() else {
        return mounts;
    };

    for item in items {
        if let Some(spec) = item.as_str() {
            if let Some(mount) = parse_volume_spec(spec) {
                mounts.push(mount);
            }
            continue;
        }
        let Some(map) = item.as_mapping() else {
            continue;
        };
        let mount_type = map
            .get(YamlValue::String("type".to_string()))
            .and_then(yaml_scalar_to_string)
            .map(|value| value.to_ascii_lowercase());
        let source = map
            .get(YamlValue::String("source".to_string()))
            .and_then(yaml_scalar_to_string);
        let target = map
            .get(YamlValue::String("target".to_string()))
            .and_then(yaml_scalar_to_string);
        let Some(target) = target else {
            continue;
        };
        let kind = match mount_type.as_deref() {
            Some("bind") => VolumeMountKind::Bind,
            Some("tmpfs") => VolumeMountKind::Tmpfs,
            Some("volume") => {
                if source.as_deref().is_some_and(is_bind_source_hint) {
                    VolumeMountKind::Bind
                } else if source.is_some() {
                    VolumeMountKind::NamedVolume
                } else {
                    VolumeMountKind::AnonymousVolume
                }
            }
            Some(_) | None => {
                if source.as_deref().is_some_and(is_bind_source_hint) {
                    VolumeMountKind::Bind
                } else if source.is_some() {
                    VolumeMountKind::NamedVolume
                } else {
                    VolumeMountKind::AnonymousVolume
                }
            }
        };
        mounts.push(VolumeMount {
            source,
            target,
            kind,
        });
    }

    mounts.sort_by(|left, right| {
        left.target
            .cmp(&right.target)
            .then(left.kind.cmp(&right.kind))
            .then(left.source.cmp(&right.source))
    });
    mounts.dedup_by(|left, right| {
        left.source == right.source && left.target == right.target && left.kind == right.kind
    });
    mounts
}

fn parse_volume_spec(spec: &str) -> Option<VolumeMount> {
    let trimmed = spec.trim();
    if trimmed.is_empty() {
        return None;
    }

    let parts: Vec<&str> = trimmed.split(':').collect();
    if parts.is_empty() {
        return None;
    }
    if parts.len() == 1 {
        let target = parts.first()?.trim().to_string();
        if target.is_empty() {
            return None;
        }
        return Some(VolumeMount {
            source: None,
            target,
            kind: VolumeMountKind::AnonymousVolume,
        });
    }

    let source = parts.first()?.trim().to_string();
    let target = parts.get(1)?.trim().to_string();
    if target.is_empty() {
        return None;
    }
    let kind = if source.is_empty() {
        VolumeMountKind::AnonymousVolume
    } else if is_bind_source_hint(&source) {
        VolumeMountKind::Bind
    } else {
        VolumeMountKind::NamedVolume
    };
    Some(VolumeMount {
        source: if source.is_empty() {
            None
        } else {
            Some(source)
        },
        target,
        kind,
    })
}

fn collect_service_tmpfs_targets(service: &Mapping) -> std::collections::BTreeSet<String> {
    let mut targets = std::collections::BTreeSet::new();
    let Some(value) = service.get(YamlValue::String("tmpfs".to_string())) else {
        return targets;
    };

    let Some(items) = value.as_sequence() else {
        return targets;
    };

    for item in items {
        let Some(spec) = item.as_str() else {
            continue;
        };
        let target = spec.split(':').next().unwrap_or(spec).trim();
        if !target.is_empty() {
            targets.insert(target.to_string());
        }
    }
    targets
}

fn is_bind_source_hint(source: &str) -> bool {
    let value = source.trim();
    value.starts_with('/')
        || value.starts_with("./")
        || value.starts_with("../")
        || value.starts_with("~/")
        || value.starts_with("${")
        || value.contains('/')
        || value.contains('\\')
}

fn sanitize_volume_target(target: &str) -> String {
    let mut output = String::new();
    let mut prev_underscore = false;
    for ch in target.to_ascii_lowercase().chars() {
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
        return "data".to_string();
    }
    trimmed
}

fn service_read_only_disabled(service: &Mapping) -> bool {
    let value = service.get(YamlValue::String("read_only".to_string()));
    match value {
        Some(YamlValue::Bool(false)) => true,
        Some(YamlValue::String(text)) => text.trim().eq_ignore_ascii_case("false"),
        Some(YamlValue::Number(number)) => number.as_i64() == Some(0),
        _ => false,
    }
}

fn healthcheck_from_runtime(runtime: &RuntimeProfile) -> Option<ComposeHealthcheckTemplate> {
    let check = runtime.healthcheck.as_ref()?;
    if check.test.is_empty() {
        return None;
    }
    Some(ComposeHealthcheckTemplate {
        test: check.test.clone(),
        interval: check.interval_ns.and_then(ns_to_compose_duration),
        timeout: check.timeout_ns.and_then(ns_to_compose_duration),
        start_period: check.start_period_ns.and_then(ns_to_compose_duration),
        retries: check.retries,
    })
}

fn healthcheck_from_tools(profile: &ImageProfile) -> Option<ComposeHealthcheckTemplate> {
    let tool_available = |tool: &str| {
        profile
            .runtime
            .tool_details
            .get(tool)
            .map(|item| item.available)
            .unwrap_or_else(|| profile.runtime.tools.get(tool).copied().unwrap_or(false))
    };

    let port = profile
        .runtime
        .exposed_ports
        .iter()
        .filter_map(|entry| entry.split('/').next())
        .filter_map(|entry| entry.parse::<u16>().ok())
        .next();

    if matches!(port, Some(5432)) && tool_available("pg_isready") {
        return Some(ComposeHealthcheckTemplate {
            test: vec![
                "CMD-SHELL".to_string(),
                "pg_isready -U \"$${POSTGRES_USER:-postgres}\" -d \"$${POSTGRES_DB:-postgres}\" || exit 1".to_string(),
            ],
            interval: Some("10s".to_string()),
            timeout: Some("5s".to_string()),
            start_period: Some("20s".to_string()),
            retries: Some(10),
        });
    }
    if matches!(port, Some(6379)) && tool_available("redis-cli") {
        return Some(ComposeHealthcheckTemplate {
            test: vec![
                "CMD".to_string(),
                "redis-cli".to_string(),
                "ping".to_string(),
            ],
            interval: Some("10s".to_string()),
            timeout: Some("5s".to_string()),
            start_period: Some("10s".to_string()),
            retries: Some(10),
        });
    }
    if let Some(port) = port {
        if tool_available("curl") {
            return Some(ComposeHealthcheckTemplate {
                test: vec![
                    "CMD-SHELL".to_string(),
                    format!("curl -fsS http://127.0.0.1:{port}/health || exit 1"),
                ],
                interval: Some("15s".to_string()),
                timeout: Some("5s".to_string()),
                start_period: Some("15s".to_string()),
                retries: Some(5),
            });
        }
        if tool_available("wget") {
            return Some(ComposeHealthcheckTemplate {
                test: vec![
                    "CMD-SHELL".to_string(),
                    format!("wget -q --spider http://127.0.0.1:{port}/health || exit 1"),
                ],
                interval: Some("15s".to_string()),
                timeout: Some("5s".to_string()),
                start_period: Some("15s".to_string()),
                retries: Some(5),
            });
        }
    }
    None
}

fn healthcheck_uses_cmd_shell(template: &ComposeHealthcheckTemplate) -> bool {
    template
        .test
        .first()
        .is_some_and(|token| token.eq_ignore_ascii_case("CMD-SHELL"))
}

fn binds_low_port(service: &Mapping, runtime: Option<&RuntimeProfile>) -> bool {
    let service_ports = service
        .get(YamlValue::String("ports".to_string()))
        .and_then(YamlValue::as_sequence)
        .cloned()
        .unwrap_or_default();

    for item in service_ports {
        let Some(text) = item.as_str() else {
            continue;
        };
        if port_mapping_contains_low_port(text) {
            return true;
        }
    }

    runtime
        .map(|profile| {
            profile
                .exposed_ports
                .iter()
                .filter_map(|entry| entry.split('/').next())
                .filter_map(|entry| entry.parse::<u16>().ok())
                .any(|port| port < 1024)
        })
        .unwrap_or(false)
}

fn port_mapping_contains_low_port(mapping: &str) -> bool {
    let normalized = mapping.trim().trim_matches('"');
    if normalized.is_empty() {
        return false;
    }
    let candidate = normalized
        .split(':')
        .next_back()
        .unwrap_or(normalized)
        .split('/')
        .next()
        .unwrap_or(normalized);
    candidate
        .parse::<u16>()
        .map(|port| port < 1024)
        .unwrap_or(false)
}

fn has_key_path(service: &Mapping, path: &str) -> bool {
    let mut current: Option<&YamlValue> = None;
    for (index, segment) in path.split('.').enumerate() {
        if index == 0 {
            current = service.get(YamlValue::String(segment.to_string()));
            continue;
        }
        let Some(value) = current else {
            return false;
        };
        let Some(map) = value.as_mapping() else {
            return false;
        };
        current = map.get(YamlValue::String(segment.to_string()));
    }
    current.is_some()
}

fn ns_to_compose_duration(value: u64) -> Option<String> {
    if value == 0 {
        return None;
    }
    if value.is_multiple_of(1_000_000_000) {
        return Some(format!("{}s", value / 1_000_000_000));
    }
    if value.is_multiple_of(1_000_000) {
        return Some(format!("{}ms", value / 1_000_000));
    }
    Some(format!("{value}ns"))
}

fn yaml_scalar_to_string(value: &YamlValue) -> Option<String> {
    match value {
        YamlValue::String(text) => Some(text.to_string()),
        YamlValue::Number(number) => Some(number.to_string()),
        _ => None,
    }
}

fn is_root_user(user: &str) -> bool {
    let normalized = user.trim().to_ascii_lowercase();
    normalized.is_empty()
        || normalized == "root"
        || normalized == "0"
        || normalized == "0:0"
        || normalized.starts_with("0:")
}

#[derive(Debug, Clone)]
struct VolumeMount {
    source: Option<String>,
    target: String,
    kind: VolumeMountKind,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum VolumeMountKind {
    NamedVolume,
    Bind,
    AnonymousVolume,
    Tmpfs,
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use crate::model::{ImageProfile, Platform, RuntimeProfile, RuntimeSignatures};
    use serde_json::json;
    use serde_yaml::Value as YamlValue;

    use super::{
        bind_mount_targets, ensure_volume_permissions, ensure_writable_paths, parse_uid_gid,
        parse_volume_spec, synthesize_healthcheck,
    };

    fn base_profile() -> ImageProfile {
        ImageProfile {
            id: "IMG-1".to_string(),
            image: "docker.io/library/nginx:1.27".to_string(),
            docs_url: None,
            dockerfile_url: None,
            digest: None,
            config_digest: None,
            platforms: vec![Platform {
                os: "linux".to_string(),
                arch: "amd64".to_string(),
            }],
            runtime: RuntimeProfile::default(),
            sources: Vec::new(),
            notes: Vec::new(),
            researched_config: Default::default(),
        }
    }

    #[test]
    fn parse_uid_gid_handles_uid_and_uid_gid_inputs() {
        assert_eq!(parse_uid_gid("1000"), Some((1000, 1000)));
        assert_eq!(parse_uid_gid("1000:2000"), Some((1000, 2000)));
        assert_eq!(parse_uid_gid("postgres"), None);
    }

    #[test]
    fn parse_volume_spec_accepts_standard_source_target_mode_form() {
        let mount =
            parse_volume_spec("uploads:/var/lib/app/uploads:rw").expect("volume spec should parse");
        assert_eq!(mount.source.as_deref(), Some("uploads"));
        assert_eq!(mount.target, "/var/lib/app/uploads");
    }

    #[test]
    fn yaml_scalar_to_string_handles_numbers() {
        let value = YamlValue::Number(3.into());
        assert_eq!(super::yaml_scalar_to_string(&value).as_deref(), Some("3"));
    }

    #[test]
    fn ensure_volume_permissions_uses_conditional_chown_script() {
        let service: YamlValue = serde_yaml::from_str(
            r#"
user: "1000:1000"
volumes:
  - data:/data
"#,
        )
        .expect("yaml should parse");
        let mapping = service
            .as_mapping()
            .expect("service value should be a mapping");
        let patches = ensure_volume_permissions("api", mapping, None).expect("heuristic runs");
        let command = patches
            .first()
            .and_then(|patch| patch.value.get("command"))
            .and_then(|command| command.as_array())
            .and_then(|tokens| tokens.last())
            .and_then(|value| value.as_str())
            .expect("init command should exist");
        assert!(command.contains("stat -c '%u:%g'"));
        assert!(command.contains("if [ \"$owner\" != \"1000:1000\" ]"));
    }

    #[test]
    fn bind_mount_targets_returns_detected_bind_targets() {
        let service: YamlValue = serde_yaml::from_str(
            r#"
volumes:
  - ./host-data:/data
  - type: bind
    source: /var/log
    target: /app/log
  - type: volume
    source: named-data
    target: /state
"#,
        )
        .expect("yaml should parse");
        let mapping = service
            .as_mapping()
            .expect("service value should be a mapping");
        let targets = bind_mount_targets(mapping);
        assert_eq!(targets, vec!["/app/log".to_string(), "/data".to_string()]);
    }

    #[test]
    fn ensure_volume_permissions_skips_bind_mounts() {
        let service: YamlValue = serde_yaml::from_str(
            r#"
user: "1000:1000"
volumes:
  - ./host-data:/data
"#,
        )
        .expect("yaml should parse");
        let mapping = service
            .as_mapping()
            .expect("service value should be a mapping");
        let patches = ensure_volume_permissions("api", mapping, None).expect("heuristic runs");
        assert!(patches.is_empty());
    }

    #[test]
    fn ensure_writable_paths_adds_tmpfs_and_required_named_volumes() {
        let service: YamlValue = serde_yaml::from_str(
            r#"
read_only: true
"#,
        )
        .expect("yaml should parse");
        let mapping = service
            .as_mapping()
            .expect("service value should be a mapping");

        let mut profile = base_profile();
        profile.researched_config.required_mounts = vec!["/var/lib/postgresql/data".to_string()];
        profile.runtime.volumes = vec!["/cache".to_string()];
        let patches = ensure_writable_paths("db", mapping, Some(&profile));

        assert!(patches
            .iter()
            .any(|patch| patch.path == "services.db.tmpfs" && patch.op == "list_add"));
        assert!(patches.iter().any(|patch| {
            patch.path == "volumes.db_var_lib_postgresql_data"
                && patch.op == "set_root"
                && patch.value == json!({})
        }));
        assert!(patches.iter().any(|patch| {
            patch.path == "services.db.volumes"
                && patch.value == json!("db_var_lib_postgresql_data:/var/lib/postgresql/data")
        }));
    }

    #[test]
    fn synthesize_healthcheck_skips_shell_templates_for_distroless_profiles() {
        let mut profile = base_profile();
        profile.runtime.exposed_ports = vec!["8080/tcp".to_string()];
        profile.runtime.tools = BTreeMap::from([("curl".to_string(), true)]);
        profile.runtime.signatures = RuntimeSignatures {
            distroless: true,
            ..RuntimeSignatures::default()
        };
        let service = YamlValue::Mapping(serde_yaml::Mapping::new());
        let mapping = service
            .as_mapping()
            .expect("service value should be a mapping");
        let patches = synthesize_healthcheck("api", mapping, Some(&profile));
        assert!(patches.is_empty());
    }
}
