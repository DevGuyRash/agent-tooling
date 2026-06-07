use std::path::PathBuf;
use std::process::{Command, Stdio};

fn fixtures_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../architect-core/tests/golden")
}

fn references_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../plugins/docker-architect/skills/docker-architect/references")
}

fn run_policy_check(
    input: PathBuf,
    policy: PathBuf,
    cache_dir: PathBuf,
) -> std::process::ExitStatus {
    Command::new(env!("CARGO_BIN_EXE_docker-architect-compose"))
        .arg("policy-check")
        .arg(input)
        .arg("--policy")
        .arg(policy)
        .arg("--cache-dir")
        .arg(cache_dir)
        .arg("--mode")
        .arg("compose")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .expect("policy-check should execute")
}

#[test]
fn policy_check_returns_exit_code_2_when_blocked_violations_exist() {
    let fixture_dir = fixtures_root().join("compose_dual");
    let status = run_policy_check(
        fixture_dir.join("input.compose.yaml"),
        references_root().join("policy-compose-enforcing.yaml"),
        fixture_dir.join("cache"),
    );
    assert_eq!(status.code(), Some(2));
}

#[test]
fn policy_check_returns_exit_code_0_when_blocked_violations_are_absent() {
    let fixture_dir = fixtures_root().join("compose_dual");
    let status = run_policy_check(
        fixture_dir.join("input.compose.yaml"),
        references_root().join("policy-compose-balanced.yaml"),
        fixture_dir.join("cache"),
    );
    assert_eq!(status.code(), Some(0));
}
