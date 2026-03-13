//! Runtime verification helpers for generated compose outputs.

use std::collections::hash_map::DefaultHasher;
use std::collections::BTreeSet;
use std::hash::{Hash, Hasher};
use std::path::Path;
use std::process::{Command, Output, Stdio};
use std::thread;
use std::time::SystemTime;
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::Value;

use crate::error::AppError;

const DOCKER_VERIFY_TIMEOUT: Duration = Duration::from_secs(45);
const DOCKER_LOGS_TIMEOUT: Duration = Duration::from_secs(20);
const DOCKER_HEALTH_WAIT_TIMEOUT: Duration = Duration::from_secs(60);
const PROCESS_POLL_INTERVAL: Duration = Duration::from_millis(50);
const READINESS_POLL_INTERVAL: Duration = Duration::from_secs(1);

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
    /// Whether `docker compose up -d` completed successfully.
    pub compose_up_succeeded: bool,
    /// Captured stderr from `docker compose up -d` when startup failed.
    pub compose_up_stderr: Option<String>,
    /// Best-effort list of services that did not reach a healthy running state.
    pub failed_services: Vec<String>,
    /// Recent compose log output captured during startup failure.
    pub service_logs_excerpt: Option<String>,
    /// Whether teardown was attempted.
    pub teardown_attempted: bool,
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

#[derive(Debug, Clone, PartialEq, Eq)]
struct ServiceReadinessRecord {
    service: String,
    container_id: String,
    running: bool,
    health_status: Option<String>,
    healthcheck_defined: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum ServiceReadiness {
    Ready,
    Pending,
    Failed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum ComposeReadinessStatus {
    Ready,
    TimedOut,
    Failed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ComposeReadinessObservation {
    status: ComposeReadinessStatus,
    services: Vec<ServiceReadinessRecord>,
    failed_services: Vec<String>,
}

#[derive(Debug, Clone)]
struct ComposeInvocationContext {
    compose_file: String,
    project_name: String,
}

/// Verify a compose file by running containers, waiting for startup readiness, collecting inspect
/// facts, and emitting a report.
/// This is a baseline hardening gate with bounded health waiting for stateful services.
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
/// * Runs `docker compose up -d` and waits up to 60 seconds for services with healthchecks to
///   report `healthy`.
/// * Services without healthchecks are considered ready once they are running.
pub fn verify_compose(
    compose_file: &Path,
    teardown: bool,
) -> Result<ComposeVerifyReport, AppError> {
    let context = compose_invocation_context(compose_file)?;
    let _ = run_compose_command(&context, &["down", "--volumes", "--remove-orphans"]);
    run_compose_command(&context, &["config", "-q"])?;
    let up_output = run_compose_output(&context, &["up", "-d"])?;
    if !up_output.status.success() {
        let failed_services = collect_failed_services(&context);
        let service_logs_excerpt = collect_compose_logs_excerpt(&context);
        let report = ComposeVerifyReport {
            mode: "compose".to_string(),
            input: compose_file.display().to_string(),
            services: Vec::new(),
            success: false,
            compose_up_succeeded: false,
            compose_up_stderr: trim_to_option(String::from_utf8_lossy(&up_output.stderr)),
            failed_services,
            service_logs_excerpt,
            teardown_attempted: false,
        };
        return finalize_report_with_optional_teardown(Ok(report), teardown, || {
            let _ = run_compose_command(&context, &["down", "--volumes", "--remove-orphans"]);
        });
    }

    let report_result = (|| {
        let readiness = wait_for_compose_readiness(&context)?;
        let mut report = collect_compose_runtime_report(&context, false)?;
        if readiness.status != ComposeReadinessStatus::Ready {
            report.success = false;
        }
        merge_failed_services(&mut report.failed_services, &readiness.failed_services);
        if !report.success && report.service_logs_excerpt.is_none() {
            report.service_logs_excerpt = collect_compose_logs_excerpt(&context);
        }
        Ok(report)
    })();

    finalize_report_with_optional_teardown(report_result, teardown, || {
        let _ = run_compose_command(&context, &["down", "--volumes", "--remove-orphans"]);
    })
}

fn collect_compose_runtime_report(
    context: &ComposeInvocationContext,
    teardown_attempted: bool,
) -> Result<ComposeVerifyReport, AppError> {
    let ps_output = run_compose_command(context, &["ps", "-q"])?;
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
    let mut failed_services: Vec<String> = services
        .iter()
        .filter(|service| !service.baseline_pass)
        .map(|service| service.service.clone())
        .collect();
    failed_services.sort();
    failed_services.dedup();
    let success = !services.is_empty() && failed_services.is_empty();
    Ok(ComposeVerifyReport {
        mode: "compose".to_string(),
        input: context.compose_file.clone(),
        services,
        success,
        compose_up_succeeded: true,
        compose_up_stderr: None,
        service_logs_excerpt: if success {
            None
        } else {
            collect_compose_logs_excerpt(context)
        },
        failed_services,
        teardown_attempted,
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

fn wait_for_compose_readiness(
    context: &ComposeInvocationContext,
) -> Result<ComposeReadinessObservation, AppError> {
    wait_for_compose_readiness_with(DOCKER_HEALTH_WAIT_TIMEOUT, READINESS_POLL_INTERVAL, || {
        collect_service_readiness_records(context)
    })
}

fn wait_for_compose_readiness_with<F>(
    timeout: Duration,
    poll_interval: Duration,
    mut fetch: F,
) -> Result<ComposeReadinessObservation, AppError>
where
    F: FnMut() -> Result<Vec<ServiceReadinessRecord>, AppError>,
{
    let start = Instant::now();
    loop {
        let services = fetch()?;
        let (status, failed_services) = summarize_compose_readiness(&services);
        match status {
            ComposeReadinessStatus::Ready | ComposeReadinessStatus::Failed => {
                return Ok(ComposeReadinessObservation {
                    status,
                    services,
                    failed_services,
                });
            }
            ComposeReadinessStatus::TimedOut => {}
        }

        if start.elapsed() >= timeout {
            return Ok(ComposeReadinessObservation {
                status: ComposeReadinessStatus::TimedOut,
                services,
                failed_services,
            });
        }
        thread::sleep(poll_interval);
    }
}

fn collect_service_readiness_records(
    context: &ComposeInvocationContext,
) -> Result<Vec<ServiceReadinessRecord>, AppError> {
    let ps_output = run_compose_command(context, &["ps", "-q"])?;
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
        let Some(record) = readiness_record_from_value(id, &value) else {
            continue;
        };
        services.push(record);
    }
    services.sort_by(|left, right| left.service.cmp(&right.service));
    Ok(services)
}

fn readiness_record_from_value(
    container_id: &str,
    value: &Value,
) -> Option<ServiceReadinessRecord> {
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

    Some(ServiceReadinessRecord {
        service,
        container_id: container_id.to_string(),
        running,
        health_status,
        healthcheck_defined,
    })
}

fn summarize_compose_readiness(
    services: &[ServiceReadinessRecord],
) -> (ComposeReadinessStatus, Vec<String>) {
    if services.is_empty() {
        return (ComposeReadinessStatus::TimedOut, Vec::new());
    }

    let mut pending = false;
    let mut failed_services = BTreeSet::new();
    for service in services {
        match classify_service_readiness(service) {
            ServiceReadiness::Ready => {}
            ServiceReadiness::Pending => pending = true,
            ServiceReadiness::Failed => {
                failed_services.insert(service.service.clone());
            }
        }
    }

    if !failed_services.is_empty() {
        return (
            ComposeReadinessStatus::Failed,
            failed_services.into_iter().collect(),
        );
    }

    if pending {
        return (ComposeReadinessStatus::TimedOut, Vec::new());
    }

    (ComposeReadinessStatus::Ready, Vec::new())
}

fn classify_service_readiness(service: &ServiceReadinessRecord) -> ServiceReadiness {
    if !service.running {
        return ServiceReadiness::Failed;
    }
    if !service.healthcheck_defined {
        return ServiceReadiness::Ready;
    }

    match service.health_status.as_deref() {
        Some("healthy") => ServiceReadiness::Ready,
        Some("unhealthy") => ServiceReadiness::Failed,
        Some("starting") | None => ServiceReadiness::Pending,
        Some(_) => ServiceReadiness::Pending,
    }
}

fn merge_failed_services(target: &mut Vec<String>, source: &[String]) {
    target.extend(source.iter().cloned());
    target.sort();
    target.dedup();
}

fn logs_contain_error_keywords(logs: &str) -> bool {
    let filtered = filter_known_benign_log_lines(logs);
    let lower = filtered.to_ascii_lowercase();
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
        line_contains_standalone_error_token(trimmed)
            || line_contains_bracketed_error_token(trimmed)
            || line_has_logfmt_error_level(trimmed)
            || trimmed.contains("] error")
    })
}

fn filter_known_benign_log_lines(logs: &str) -> String {
    logs.lines()
        .filter(|line| !is_known_benign_postgres_bootstrap_line(line))
        .collect::<Vec<_>>()
        .join("\n")
}

fn is_known_benign_postgres_bootstrap_line(line: &str) -> bool {
    let lower = line.to_ascii_lowercase();
    lower.contains("fatal:  the database system is starting up")
        || lower.contains("fatal: the database system is starting up")
        || lower.contains("fatal:  the database system is shutting down")
        || lower.contains("fatal: the database system is shutting down")
}

fn line_contains_bracketed_error_token(line: &str) -> bool {
    const NEEDLE: &str = "[error]";
    line.match_indices(NEEDLE).any(|(index, _)| {
        if index_inside_unescaped_double_quotes(line, index) {
            return false;
        }

        let boundary_before_ok = if index == 0 {
            true
        } else {
            line[..index].chars().next_back().is_some_and(|character| {
                character.is_ascii_whitespace()
                    || matches!(character, ']' | ')' | '}' | '>' | ':' | ',' | ';')
            })
        };

        boundary_before_ok && line_has_bracketed_error_prefix(&line[index..])
    })
}

fn line_contains_standalone_error_token(line: &str) -> bool {
    const NEEDLE: &str = "error";
    line.match_indices(NEEDLE).any(|(index, _)| {
        if index_inside_unescaped_double_quotes(line, index) {
            return false;
        }

        let boundary_before_ok = if index == 0 {
            true
        } else {
            line[..index].chars().next_back().is_some_and(|character| {
                character.is_ascii_whitespace()
                    || matches!(
                        character,
                        '[' | '(' | '{' | '<' | ']' | ')' | '}' | '>' | ':' | ',' | ';'
                    )
            })
        };
        if !boundary_before_ok {
            return false;
        }

        line_has_standalone_error_prefix(&line[index..])
    })
}

fn line_has_logfmt_error_level(line: &str) -> bool {
    const NEEDLE: &str = "level=error";
    line.match_indices(NEEDLE).any(|(index, _)| {
        if index_inside_unescaped_double_quotes(line, index) {
            return false;
        }

        let boundary_before_ok = if index == 0 {
            true
        } else {
            line[..index]
                .chars()
                .next_back()
                .is_some_and(|character| character.is_ascii_whitespace())
        };
        if !boundary_before_ok {
            return false;
        }

        let suffix = &line[index + NEEDLE.len()..];
        match suffix.chars().next() {
            None => true,
            Some(character) => {
                character.is_ascii_whitespace() || matches!(character, ',' | ';' | ']' | '}')
            }
        }
    })
}

fn index_inside_unescaped_double_quotes(line: &str, byte_index: usize) -> bool {
    let mut inside_quotes = false;
    let mut escaped = false;

    for (index, character) in line.char_indices() {
        if index >= byte_index {
            break;
        }

        if escaped {
            escaped = false;
            continue;
        }

        if inside_quotes && character == '\\' {
            escaped = true;
            continue;
        }

        if character == '"' {
            inside_quotes = !inside_quotes;
        }
    }

    inside_quotes
}

fn line_has_bracketed_error_prefix(line: &str) -> bool {
    let Some(remainder) = line.strip_prefix("[error]") else {
        return false;
    };
    if remainder.is_empty() {
        return true;
    }
    remainder
        .chars()
        .next()
        .is_some_and(|c| c.is_ascii_whitespace() || c == ':')
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
        "tolerance" | "correction" | "rate" | "rates" | "count" | "counts" | "0"
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

fn run_compose_command(
    context: &ComposeInvocationContext,
    args: &[&str],
) -> Result<String, AppError> {
    let output = run_compose_output(context, args)?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let exit_status = format_exit_status(&output.status);
        return Err(AppError::InvalidInput {
            reason: format!(
                "docker command failed `compose -p {} -f {} {}` (exit {}): {}",
                context.project_name,
                context.compose_file,
                args.join(" "),
                exit_status,
                stderr
            ),
        });
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn run_compose_output(
    context: &ComposeInvocationContext,
    args: &[&str],
) -> Result<Output, AppError> {
    let mut full_args = vec![
        "compose",
        "-p",
        &context.project_name,
        "-f",
        &context.compose_file,
    ];
    full_args.extend(args.iter().copied());
    run_docker_output(&full_args, DOCKER_VERIFY_TIMEOUT).map_err(|error| AppError::InvalidInput {
        reason: format!(
            "failed to execute docker command `compose -p {} -f {} {}`: {}",
            context.project_name,
            context.compose_file,
            args.join(" "),
            error
        ),
    })
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
        let exit_status = format_exit_status(&output.status);
        return Err(AppError::InvalidInput {
            reason: format!(
                "docker command failed `{}` (exit {}): {}",
                args.join(" "),
                exit_status,
                stderr
            ),
        });
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn format_exit_status(status: &std::process::ExitStatus) -> String {
    if let Some(code) = status.code() {
        return code.to_string();
    }

    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;

        if let Some(signal) = status.signal() {
            return format!("signal {signal}");
        }
    }

    "unknown".to_string()
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

fn collect_failed_services(context: &ComposeInvocationContext) -> Vec<String> {
    let Ok(output) = run_compose_output(context, &["ps", "--all", "--format", "json"]) else {
        return Vec::new();
    };
    let stdout = String::from_utf8_lossy(&output.stdout);
    parse_failed_services_from_compose_ps(&stdout)
}

fn parse_failed_services_from_compose_ps(stdout: &str) -> Vec<String> {
    let trimmed = stdout.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }

    let mut failed = std::collections::BTreeSet::new();
    let rows = if trimmed.starts_with('[') {
        serde_json::from_str::<Vec<Value>>(trimmed).unwrap_or_default()
    } else {
        trimmed
            .lines()
            .filter_map(|line| serde_json::from_str::<Value>(line).ok())
            .collect()
    };

    for row in rows {
        let service = row
            .get("Service")
            .or_else(|| row.get("Name"))
            .and_then(Value::as_str)
            .unwrap_or_default();
        let state = row
            .get("State")
            .or_else(|| row.get("Status"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_ascii_lowercase();
        if service.is_empty() {
            continue;
        }
        if ["exited", "dead", "created", "restarting", "removing"]
            .iter()
            .any(|status| state.contains(status))
        {
            failed.insert(service.to_string());
        }
    }

    failed.into_iter().collect()
}

fn collect_compose_logs_excerpt(context: &ComposeInvocationContext) -> Option<String> {
    let Ok(output) = run_compose_output(context, &["logs", "--tail=50"]) else {
        return None;
    };
    let combined = format!(
        "{}{}{}",
        String::from_utf8_lossy(&output.stdout),
        if output.stdout.is_empty() || output.stderr.is_empty() {
            ""
        } else {
            "\n"
        },
        String::from_utf8_lossy(&output.stderr)
    );
    trim_to_option(combined)
}

fn trim_to_option(value: impl AsRef<str>) -> Option<String> {
    let trimmed = value.as_ref().trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}

fn finalize_report_with_optional_teardown<F>(
    report_result: Result<ComposeVerifyReport, AppError>,
    teardown: bool,
    mut teardown_fn: F,
) -> Result<ComposeVerifyReport, AppError>
where
    F: FnMut(),
{
    if teardown {
        teardown_fn();
    }

    match report_result {
        Ok(report) => Ok(ComposeVerifyReport {
            teardown_attempted: teardown,
            ..report
        }),
        Err(error) => Err(error),
    }
}

fn compose_invocation_context(compose_file: &Path) -> Result<ComposeInvocationContext, AppError> {
    let compose_file = compose_file
        .canonicalize()
        .map_err(|error| AppError::io(compose_file, error.to_string()))?;
    let compose_file_string = compose_file.display().to_string();
    let mut hasher = DefaultHasher::new();
    compose_file_string.hash(&mut hasher);
    std::process::id().hash(&mut hasher);
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or_default()
        .hash(&mut hasher);
    let hash = hasher.finish();
    Ok(ComposeInvocationContext {
        compose_file: compose_file_string,
        project_name: format!("docker-architect-{hash:016x}"),
    })
}

#[cfg(test)]
mod tests {
    use std::collections::VecDeque;
    use std::time::Duration;

    #[cfg(unix)]
    use std::os::unix::process::ExitStatusExt;

    use serde_json::json;

    use crate::error::AppError;

    use super::{
        classify_service_readiness, finalize_report_with_optional_teardown, format_exit_status,
        inspect_record_from_value, is_root_user, logs_contain_error_keywords,
        parse_failed_services_from_compose_ps, readiness_record_from_value,
        summarize_compose_readiness, trim_to_option, wait_for_compose_readiness_with,
        ComposeReadinessStatus, ComposeVerifyReport, ServiceReadiness, ServiceReadinessRecord,
    };

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
        assert!(logs_contain_error_keywords("[ERROR] failed to connect"));
        assert!(logs_contain_error_keywords("[ERROR]: failed to connect"));
        assert!(logs_contain_error_keywords("[ERROR]"));
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
        assert!(logs_contain_error_keywords(
            "level=error msg=\"unable to bind\""
        ));
        assert!(logs_contain_error_keywords(
            "ts=2026-02-22T10:00:00Z level=error msg=\"unable to bind\""
        ));
        assert!(logs_contain_error_keywords(
            "2026-02-22T10:00:00Z ERROR: unable to bind"
        ));
        assert!(logs_contain_error_keywords(
            "2026-02-22T10:00:00Z [ERROR] failed to connect"
        ));
        assert!(!logs_contain_error_keywords("error tolerance: none"));
        assert!(!logs_contain_error_keywords("error correction disabled"));
        assert!(!logs_contain_error_keywords("error: 0"));
        assert!(!logs_contain_error_keywords("error count: 0"));
        assert!(!logs_contain_error_keywords("error,count: 0"));
        assert!(!logs_contain_error_keywords(
            "msg=\"set level=error for test coverage\" level=info"
        ));
        assert!(!logs_contain_error_keywords("[ERROR]abc"));
        assert!(!logs_contain_error_keywords("[errors] found"));
        assert!(!logs_contain_error_keywords("errors found: 0"));
        assert!(!logs_contain_error_keywords("healthy: 0 errors found"));
        assert!(!logs_contain_error_keywords("ready and healthy"));
        assert!(!logs_contain_error_keywords(
            "postgres: FATAL:  the database system is shutting down"
        ));
        assert!(!logs_contain_error_keywords(
            "postgres: FATAL: the database system is starting up"
        ));
        assert!(logs_contain_error_keywords(
            "postgres: FATAL:  role \"citest\" does not exist"
        ));
        assert!(logs_contain_error_keywords(
            "chmod: /var/run/postgresql: Operation not permitted"
        ));
    }

    #[cfg(unix)]
    #[test]
    fn format_exit_status_reports_signal_termination() {
        let status = std::process::ExitStatus::from_raw(9);
        assert_eq!(format_exit_status(&status), "signal 9");
    }

    #[test]
    fn parse_failed_services_from_compose_ps_accepts_json_lines() {
        let stdout = r#"{"Service":"api","State":"exited"}
{"Service":"worker","State":"running"}
{"Service":"db","State":"restarting"}"#;
        let failed = parse_failed_services_from_compose_ps(stdout);
        assert_eq!(failed, vec!["api".to_string(), "db".to_string()]);
    }

    #[test]
    fn trim_to_option_discards_blank_strings() {
        assert_eq!(trim_to_option("   "), None);
        assert_eq!(trim_to_option(" stderr "), Some("stderr".to_string()));
    }

    #[test]
    fn classify_service_readiness_handles_health_states() {
        let ready = ServiceReadinessRecord {
            service: "db".to_string(),
            container_id: "abc".to_string(),
            running: true,
            health_status: Some("healthy".to_string()),
            healthcheck_defined: true,
        };
        assert_eq!(classify_service_readiness(&ready), ServiceReadiness::Ready);

        let pending = ServiceReadinessRecord {
            health_status: Some("starting".to_string()),
            ..ready.clone()
        };
        assert_eq!(
            classify_service_readiness(&pending),
            ServiceReadiness::Pending
        );

        let failed = ServiceReadinessRecord {
            health_status: Some("unhealthy".to_string()),
            ..ready
        };
        assert_eq!(
            classify_service_readiness(&failed),
            ServiceReadiness::Failed
        );
    }

    #[test]
    fn summarize_compose_readiness_reports_failed_services() {
        let records = vec![
            ServiceReadinessRecord {
                service: "api".to_string(),
                container_id: "1".to_string(),
                running: true,
                health_status: Some("healthy".to_string()),
                healthcheck_defined: true,
            },
            ServiceReadinessRecord {
                service: "db".to_string(),
                container_id: "2".to_string(),
                running: false,
                health_status: Some("starting".to_string()),
                healthcheck_defined: true,
            },
        ];
        let (status, failed) = summarize_compose_readiness(&records);
        assert_eq!(status, ComposeReadinessStatus::Failed);
        assert_eq!(failed, vec!["db".to_string()]);
    }

    #[test]
    fn wait_for_compose_readiness_with_times_out_for_pending_health() {
        let mut snapshots = VecDeque::from([vec![ServiceReadinessRecord {
            service: "db".to_string(),
            container_id: "abc".to_string(),
            running: true,
            health_status: Some("starting".to_string()),
            healthcheck_defined: true,
        }]]);
        let observation = wait_for_compose_readiness_with(Duration::ZERO, Duration::ZERO, || {
            Ok(snapshots.pop_front().unwrap_or_default())
        })
        .expect("wait should succeed");
        assert_eq!(observation.status, ComposeReadinessStatus::TimedOut);
        assert!(observation.failed_services.is_empty());
    }

    #[test]
    fn wait_for_compose_readiness_with_returns_ready_after_transition() {
        let mut snapshots = VecDeque::from([
            vec![ServiceReadinessRecord {
                service: "db".to_string(),
                container_id: "abc".to_string(),
                running: true,
                health_status: Some("starting".to_string()),
                healthcheck_defined: true,
            }],
            vec![ServiceReadinessRecord {
                service: "db".to_string(),
                container_id: "abc".to_string(),
                running: true,
                health_status: Some("healthy".to_string()),
                healthcheck_defined: true,
            }],
        ]);
        let observation =
            wait_for_compose_readiness_with(Duration::from_secs(1), Duration::ZERO, || {
                Ok(snapshots.pop_front().unwrap_or_default())
            })
            .expect("wait should succeed");
        assert_eq!(observation.status, ComposeReadinessStatus::Ready);
    }

    #[test]
    fn readiness_record_from_value_reads_health_fields() {
        let payload = json!([
          {
            "Config": {
              "Labels": { "com.docker.compose.service": "db" },
              "Healthcheck": { "Test": ["CMD", "true"] }
            },
            "State": {
              "Running": true,
              "Health": { "Status": "healthy" }
            }
          }
        ]);
        let record =
            readiness_record_from_value("container-id", &payload).expect("record should parse");
        assert_eq!(record.service, "db");
        assert_eq!(record.container_id, "container-id");
        assert!(record.running);
        assert_eq!(record.health_status.as_deref(), Some("healthy"));
        assert!(record.healthcheck_defined);
    }

    #[test]
    fn finalize_report_with_optional_teardown_marks_successful_reports() {
        let mut teardown_called = false;
        let result = finalize_report_with_optional_teardown(
            Ok(ComposeVerifyReport {
                mode: "compose".to_string(),
                input: "compose.yaml".to_string(),
                services: Vec::new(),
                success: true,
                compose_up_succeeded: true,
                compose_up_stderr: None,
                failed_services: Vec::new(),
                service_logs_excerpt: None,
                teardown_attempted: false,
            }),
            true,
            || teardown_called = true,
        )
        .expect("result should succeed");
        assert!(teardown_called);
        assert!(result.teardown_attempted);
    }

    #[test]
    fn finalize_report_with_optional_teardown_runs_on_errors() {
        let mut teardown_called = false;
        let result = finalize_report_with_optional_teardown(
            Err(AppError::InvalidInput {
                reason: "boom".to_string(),
            }),
            true,
            || teardown_called = true,
        );
        assert!(teardown_called);
        assert!(matches!(result, Err(AppError::InvalidInput { .. })));
    }
}
