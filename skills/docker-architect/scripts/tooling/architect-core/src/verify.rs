//! Runtime verification helpers for generated compose outputs.

use std::path::Path;
use std::process::{Command, Output, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::Value;

use crate::error::AppError;

const DOCKER_VERIFY_TIMEOUT: Duration = Duration::from_secs(45);
const DOCKER_LOGS_TIMEOUT: Duration = Duration::from_secs(20);
const PROCESS_POLL_INTERVAL: Duration = Duration::from_millis(50);

/// Verification report for compose runtime checks.
#[derive(Debug, Clone, Serialize)]
pub struct ComposeVerifyReport {
    /// Verification mode.
    pub mode: String,
    /// Compose file path used for verification.
    pub input: String,
    /// Service-level runtime observations.
    pub services: Vec<ServiceVerifyRecord>,
    /// Whether all required checks passed.
    pub success: bool,
}

/// Verification details for one resolved container/service.
#[derive(Debug, Clone, Serialize)]
pub struct ServiceVerifyRecord {
    /// Compose service name.
    pub service: String,
    /// Container ID inspected for this service.
    pub container_id: String,
    /// Whether container state is running.
    pub running: bool,
    /// Optional Docker health status.
    pub health_status: Option<String>,
    /// Whether this container has a healthcheck configured.
    pub healthcheck_defined: bool,
    /// Configured container user from inspect.
    pub configured_user: Option<String>,
    /// Whether configured user is non-root.
    pub non_root_user: bool,
    /// Whether root filesystem is read-only.
    pub read_only_rootfs: bool,
    /// Whether capabilities include `ALL` in cap-drop set.
    pub cap_drop_all: bool,
    /// Whether no-new-privileges runtime hardening is enabled.
    pub no_new_privileges: bool,
    /// Whether container is running privileged.
    pub privileged: bool,
    /// Whether recent logs contain high-signal error keywords.
    pub logs_contain_errors: bool,
    /// Baseline hardening compliance pass/fail for this service.
    pub baseline_pass: bool,
}

/// Verify a compose file by running containers, collecting inspect facts, and emitting a report.
/// This is a baseline hardening gate, not a readiness waiter.
///
/// # Arguments
/// * `compose_file` - Compose yaml file path.
/// * `teardown` - Whether to run `docker compose down` after checks.
///
/// # Returns
/// * `Ok(ComposeVerifyReport)` when commands execute successfully.
/// * `Err(AppError)` when docker commands or inspect parsing fail.
///
/// # Behavior Notes
/// * Runs `docker compose up -d` and immediately inspects current state.
/// * Does not wait/poll for health transitions; services with healthchecks may still be `starting`.
pub fn verify_compose(
    compose_file: &Path,
    teardown: bool,
) -> Result<ComposeVerifyReport, AppError> {
    run_compose_command(compose_file, &["config", "-q"])?;
    run_compose_command(compose_file, &["up", "-d"])?;

    let verify_result = collect_compose_runtime_report(compose_file);
    if teardown {
        let _ = run_compose_command(compose_file, &["down", "--volumes"]);
    }
    verify_result
}

fn collect_compose_runtime_report(compose_file: &Path) -> Result<ComposeVerifyReport, AppError> {
    let ps_output = run_compose_command(compose_file, &["ps", "-q"])?;
    let ids: Vec<&str> = ps_output
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect();

    let mut services = Vec::new();
    for id in ids {
        let inspect = run_docker_command(&["inspect", id])?;
        let value: Value =
            serde_json::from_str(&inspect).map_err(|error| AppError::InvalidInput {
                reason: format!("failed to parse docker inspect output: {error}"),
            })?;
        let logs_contain_errors = scan_container_logs_for_errors(id, 50)?;
        let Some(record) = inspect_record_from_value(id, &value, logs_contain_errors) else {
            continue;
        };
        services.push(record);
    }
    services.sort_by(|left, right| left.service.cmp(&right.service));
    let success = !services.is_empty() && services.iter().all(|service| service.baseline_pass);
    Ok(ComposeVerifyReport {
        mode: "compose".to_string(),
        input: compose_file.display().to_string(),
        services,
        success,
    })
}

fn inspect_record_from_value(
    container_id: &str,
    value: &Value,
    logs_contain_errors: bool,
) -> Option<ServiceVerifyRecord> {
    let item = value.as_array()?.first()?;
    let service = item
        .pointer("/Config/Labels/com.docker.compose.service")
        .and_then(Value::as_str)
        .unwrap_or("unknown")
        .to_string();
    let running = item
        .pointer("/State/Running")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let health_status = item
        .pointer("/State/Health/Status")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned);
    let healthcheck_defined = item.pointer("/Config/Healthcheck").is_some();
    let configured_user = item
        .pointer("/Config/User")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
        .filter(|value| !value.is_empty());
    let read_only_rootfs = item
        .pointer("/HostConfig/ReadonlyRootfs")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let cap_drop_all = item
        .pointer("/HostConfig/CapDrop")
        .and_then(Value::as_array)
        .is_some_and(|caps| caps.iter().any(|cap| cap.as_str() == Some("ALL")));
    let no_new_privileges = item
        .pointer("/HostConfig/SecurityOpt")
        .and_then(Value::as_array)
        .is_some_and(|options| {
            options
                .iter()
                .filter_map(Value::as_str)
                .any(|option| option == "no-new-privileges:true")
        });
    let privileged = item
        .pointer("/HostConfig/Privileged")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let non_root_user = configured_user
        .as_deref()
        .is_some_and(|value| !is_root_user(value));
    let healthy_or_not_required =
        !healthcheck_defined || matches!(health_status.as_deref(), Some("healthy"));

    let baseline_pass = running
        && non_root_user
        && read_only_rootfs
        && cap_drop_all
        && no_new_privileges
        && !privileged
        && !logs_contain_errors
        && healthy_or_not_required;

    Some(ServiceVerifyRecord {
        service,
        container_id: container_id.to_string(),
        running,
        health_status,
        healthcheck_defined,
        configured_user,
        non_root_user,
        read_only_rootfs,
        cap_drop_all,
        no_new_privileges,
        privileged,
        logs_contain_errors,
        baseline_pass,
    })
}

fn scan_container_logs_for_errors(container_id: &str, tail: usize) -> Result<bool, AppError> {
    let tail_string = tail.to_string();
    let output = run_docker_output(
        &["logs", "--tail", &tail_string, container_id],
        DOCKER_LOGS_TIMEOUT,
    )
    .map_err(|error| AppError::InvalidInput {
        reason: format!("failed to execute docker logs command for {container_id}: {error}"),
    })?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        return Ok(logs_contain_error_keywords(&format!("{stdout}\n{stderr}")));
    }
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    Ok(logs_contain_error_keywords(&format!("{stdout}\n{stderr}")))
}

fn logs_contain_error_keywords(logs: &str) -> bool {
    let lower = logs.to_ascii_lowercase();
    if [
        "panic",
        "fatal",
        "exception",
        "read-only file system",
        "permission denied",
        "operation not permitted",
    ]
    .iter()
    .any(|keyword| lower.contains(keyword))
    {
        return true;
    }

    lower.lines().any(|line| {
        let trimmed = line.trim_start();
        line_has_standalone_error_prefix(trimmed)
            || trimmed.contains(" level=error")
            || trimmed.contains("] error")
    })
}

fn line_has_standalone_error_prefix(line: &str) -> bool {
    let Some(remainder) = line.strip_prefix("error") else {
        return false;
    };
    if remainder.is_empty() {
        return true;
    }

    let Some(first_char) = remainder.chars().next() else {
        return false;
    };
    if !(first_char.is_ascii_whitespace() || first_char == ':' || first_char == ',') {
        return false;
    }
    if first_char == ':' {
        return true;
    }

    let first_token = remainder
        .trim_start_matches(|character: char| {
            character.is_ascii_whitespace() || character == ':' || character == ','
        })
        .split(|character: char| {
            character.is_ascii_whitespace() || character == ':' || character == ','
        })
        .next()
        .unwrap_or_default();
    if first_token.is_empty() {
        return true;
    }

    !matches!(
        first_token,
        "tolerance" | "correction" | "rate" | "rates" | "count" | "counts"
    )
}

fn is_root_user(user: &str) -> bool {
    let normalized = user.trim().to_ascii_lowercase();
    normalized.is_empty()
        || normalized == "root"
        || normalized == "0"
        || normalized == "0:0"
        || normalized.starts_with("0:")
}

fn run_compose_command(compose_file: &Path, args: &[&str]) -> Result<String, AppError> {
    let mut full_args = vec!["compose", "-f"];
    let compose_file_string = compose_file.display().to_string();
    full_args.push(&compose_file_string);
    full_args.extend(args.iter().copied());
    run_docker_command(&full_args)
}

fn run_docker_command(args: &[&str]) -> Result<String, AppError> {
    let output =
        run_docker_output(args, DOCKER_VERIFY_TIMEOUT).map_err(|error| AppError::InvalidInput {
            reason: format!(
                "failed to execute docker command `{}`: {error}",
                args.join(" ")
            ),
        })?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(AppError::InvalidInput {
            reason: format!(
                "docker command failed `{}` (exit {}): {}",
                args.join(" "),
                output.status.code().unwrap_or_default(),
                stderr
            ),
        });
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn run_docker_output(args: &[&str], timeout: Duration) -> Result<Output, String> {
    let mut child = Command::new("docker")
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;
    let start = Instant::now();

    loop {
        if child
            .try_wait()
            .map_err(|error| error.to_string())?
            .is_some()
        {
            return child.wait_with_output().map_err(|error| error.to_string());
        }

        if start.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!(
                "timed out after {}s: docker {}",
                timeout.as_secs(),
                args.join(" ")
            ));
        }

        thread::sleep(PROCESS_POLL_INTERVAL);
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{inspect_record_from_value, is_root_user, logs_contain_error_keywords};

    #[test]
    fn is_root_user_handles_numeric_and_named_root() {
        assert!(is_root_user("root"));
        assert!(is_root_user("0"));
        assert!(is_root_user("0:1000"));
        assert!(!is_root_user("1000:1000"));
    }

    #[test]
    fn inspect_record_from_value_requires_baseline_controls() {
        let payload = json!([
          {
            "Config": {
              "Labels": { "com.docker.compose.service": "api" },
              "User": "1000:1000",
              "Healthcheck": { "Test": ["CMD", "true"] }
            },
            "State": {
              "Running": true,
              "Health": { "Status": "healthy" }
            },
            "HostConfig": {
              "ReadonlyRootfs": true,
              "CapDrop": ["ALL"],
              "SecurityOpt": ["no-new-privileges:true"],
              "Privileged": false
            }
          }
        ]);
        let record = inspect_record_from_value("container-id", &payload, false)
            .expect("record should parse");
        assert!(record.baseline_pass);
    }

    #[test]
    fn logs_contain_error_keywords_matches_expected_terms() {
        assert!(logs_contain_error_keywords("panic: unable to bind"));
        assert!(logs_contain_error_keywords("Fatal startup error"));
        assert!(logs_contain_error_keywords("error: connection refused"));
        assert!(logs_contain_error_keywords("ERROR failed to connect"));
        assert!(logs_contain_error_keywords(" error failed to connect"));
        assert!(logs_contain_error_keywords(
            "error,details=failed to connect"
        ));
        assert!(logs_contain_error_keywords(
            "write /tmp/x: read-only file system"
        ));
        assert!(logs_contain_error_keywords(
            "open /etc/app: permission denied"
        ));
        assert!(logs_contain_error_keywords(
            "mount failed: operation not permitted"
        ));
        assert!(!logs_contain_error_keywords("error tolerance: none"));
        assert!(!logs_contain_error_keywords("error correction disabled"));
        assert!(!logs_contain_error_keywords("error count: 0"));
        assert!(!logs_contain_error_keywords("error,count: 0"));
        assert!(!logs_contain_error_keywords("errors found: 0"));
        assert!(!logs_contain_error_keywords("healthy: 0 errors found"));
        assert!(!logs_contain_error_keywords("ready and healthy"));
    }
}
