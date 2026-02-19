//! Optional local runtime probes used to enrich deterministic cache payloads.

use std::collections::BTreeMap;
use std::process::{Command, Output};
use std::thread;
use std::time::{Duration, Instant};

use regex::Regex;

use crate::error::AppError;
use crate::model::RuntimeToolDetail;

const DOCKER_PROBE_TIMEOUT: Duration = Duration::from_secs(20);
const PROCESS_POLL_INTERVAL: Duration = Duration::from_millis(50);

/// Probe tool availability for one image using `docker run`.
///
/// # Arguments
/// * `image` - Fully qualified image reference.
/// * `tools` - Tool names to evaluate.
///
/// # Returns
/// * `Ok(BTreeMap<String, RuntimeToolDetail>)` with deterministic key ordering.
/// * `Err(AppError)` if docker invocation cannot be executed.
pub fn probe_runtime_tools(
    image: &str,
    tools: &[String],
) -> Result<BTreeMap<String, RuntimeToolDetail>, AppError> {
    let valid_tool_re =
        Regex::new(r"^[A-Za-z0-9_.+-]+$").map_err(|error| AppError::InvalidInput {
            reason: format!("failed to compile probe tool regex: {error}"),
        })?;

    let mut output = BTreeMap::new();
    for tool in tools {
        if !valid_tool_re.is_match(tool) {
            output.insert(
                tool.clone(),
                RuntimeToolDetail {
                    available: false,
                    path: None,
                    strategy: Some("invalid-name".to_string()),
                },
            );
            continue;
        }

        if let Some(path) = probe_tool_without_shell(image, tool)? {
            output.insert(
                tool.clone(),
                RuntimeToolDetail {
                    available: true,
                    path: Some(path),
                    strategy: Some("entrypoint".to_string()),
                },
            );
            continue;
        }

        let shell_probe = probe_tool_with_shell(image, tool)?;
        if let Some(path) = shell_probe.path {
            output.insert(
                tool.clone(),
                RuntimeToolDetail {
                    available: true,
                    path: Some(path),
                    strategy: Some("shell-command-v".to_string()),
                },
            );
            continue;
        }

        output.insert(
            tool.clone(),
            RuntimeToolDetail {
                available: false,
                path: None,
                strategy: Some(missing_tool_strategy(tool, shell_probe.shell_missing).to_string()),
            },
        );
    }

    Ok(output)
}

fn probe_tool_without_shell(image: &str, tool: &str) -> Result<Option<String>, AppError> {
    // O(n) where n = number of candidate binary locations (expected: <= 7).
    for candidate in candidate_entrypoints(tool) {
        let output = run_entrypoint_probe(image, &candidate)?;
        let missing_binary = indicates_missing_binary(&output);
        let discovered =
            classify_entrypoint_probe(&candidate, output.status.success(), missing_binary);
        if let Some(path) = discovered {
            return Ok(Some(path));
        }
        if missing_binary {
            continue;
        }
    }
    Ok(None)
}

fn classify_entrypoint_probe(
    candidate: &str,
    success: bool,
    missing_binary: bool,
) -> Option<String> {
    if success {
        return Some(candidate.to_string());
    }
    if missing_binary {
        return None;
    }
    // Non-missing failure still proves the binary exists (invalid flag, permission, etc.).
    Some(candidate.to_string())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ShellProbeOutcome {
    path: Option<String>,
    shell_missing: bool,
}

fn probe_tool_with_shell(image: &str, tool: &str) -> Result<ShellProbeOutcome, AppError> {
    let mut missing_shell_count = 0usize;
    for shell in ["/bin/sh", "sh"] {
        let output = run_docker_probe_command(&[
            "run".to_string(),
            "--rm".to_string(),
            "--entrypoint".to_string(),
            shell.to_string(),
            image.to_string(),
            "-c".to_string(),
            format!("command -v {tool}"),
        ])?;

        if output.status.success() {
            let discovered = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !discovered.is_empty() {
                return Ok(ShellProbeOutcome {
                    path: Some(discovered),
                    shell_missing: false,
                });
            }
        }

        if indicates_missing_binary(&output) {
            missing_shell_count += 1;
            continue;
        }
    }
    Ok(ShellProbeOutcome {
        path: None,
        shell_missing: missing_shell_count == 2,
    })
}

fn candidate_entrypoints(tool: &str) -> Vec<String> {
    vec![
        format!("/usr/local/bin/{tool}"),
        format!("/usr/bin/{tool}"),
        format!("/bin/{tool}"),
        format!("/usr/sbin/{tool}"),
        format!("/sbin/{tool}"),
        tool.to_string(),
    ]
}

fn run_entrypoint_probe(image: &str, entrypoint: &str) -> Result<Output, AppError> {
    run_docker_probe_command(&[
        "run".to_string(),
        "--rm".to_string(),
        "--entrypoint".to_string(),
        entrypoint.to_string(),
        image.to_string(),
        "--help".to_string(),
    ])
}

fn run_docker_probe_command(args: &[String]) -> Result<Output, AppError> {
    let mut child =
        Command::new("docker")
            .args(args)
            .spawn()
            .map_err(|error| AppError::InvalidInput {
                reason: format!("failed to execute docker runtime probe: {error}"),
            })?;

    let start = Instant::now();
    loop {
        if child
            .try_wait()
            .map_err(|error| AppError::InvalidInput {
                reason: format!("failed while waiting for docker runtime probe: {error}"),
            })?
            .is_some()
        {
            return child
                .wait_with_output()
                .map_err(|error| AppError::InvalidInput {
                    reason: format!("failed to collect docker runtime probe output: {error}"),
                });
        }

        if start.elapsed() >= DOCKER_PROBE_TIMEOUT {
            let _ = child.kill();
            let _ = child.wait();
            return Err(AppError::InvalidInput {
                reason: format!(
                    "docker runtime probe timed out after {}s: docker {}",
                    DOCKER_PROBE_TIMEOUT.as_secs(),
                    args.join(" ")
                ),
            });
        }

        thread::sleep(PROCESS_POLL_INTERVAL);
    }
}

fn indicates_missing_binary(output: &Output) -> bool {
    let stdout = String::from_utf8_lossy(&output.stdout).to_ascii_lowercase();
    let stderr = String::from_utf8_lossy(&output.stderr).to_ascii_lowercase();
    let merged = format!("{stdout}\n{stderr}");
    merged.contains("executable file not found")
        || merged.contains("no such file or directory")
        || merged.contains("command not found")
}

fn missing_tool_strategy(tool: &str, shell_missing: bool) -> &'static str {
    if shell_missing && tool.eq_ignore_ascii_case("sh") {
        return "shell-missing-distroless-likely";
    }
    "not-found"
}

#[cfg(test)]
mod tests {
    use super::{
        candidate_entrypoints, classify_entrypoint_probe, missing_tool_strategy,
        probe_runtime_tools,
    };

    #[test]
    fn candidate_entrypoints_returns_deterministic_order() {
        let paths = candidate_entrypoints("curl");
        assert_eq!(
            paths.first().map(String::as_str),
            Some("/usr/local/bin/curl")
        );
        assert_eq!(paths.last().map(String::as_str), Some("curl"));
    }

    #[test]
    fn probe_runtime_tools_marks_invalid_tool_name_unavailable() {
        let result = probe_runtime_tools("docker.io/library/nginx:1.27", &["bad tool".to_string()])
            .expect("probe should return a map");
        let detail = result.get("bad tool").expect("tool result should exist");
        assert!(!detail.available);
        assert_eq!(detail.strategy.as_deref(), Some("invalid-name"));
    }

    #[test]
    fn missing_tool_strategy_marks_shell_missing_as_distroless_signal() {
        assert_eq!(
            missing_tool_strategy("sh", true),
            "shell-missing-distroless-likely"
        );
        assert_eq!(missing_tool_strategy("curl", true), "not-found");
    }

    #[test]
    fn classify_entrypoint_probe_treats_non_missing_failure_as_binary_present() {
        let result = classify_entrypoint_probe("/usr/bin/curl", false, false);
        assert_eq!(result.as_deref(), Some("/usr/bin/curl"));
    }
}
