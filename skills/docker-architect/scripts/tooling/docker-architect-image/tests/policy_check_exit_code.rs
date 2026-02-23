use std::path::PathBuf;
use std::process::{Command, Stdio};

fn fixtures_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../architect-core/tests/golden")
}

fn references_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../references")
}

fn run_policy_check(input: PathBuf, policy: PathBuf) -> std::process::ExitStatus {
    Command::new(env!("CARGO_BIN_EXE_docker-architect-image"))
        .arg("policy-check")
        .arg(input)
        .arg("--policy")
        .arg(policy)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .expect("policy-check should execute")
}

#[test]
fn policy_check_returns_exit_code_2_when_blocked_violations_exist() {
    let status = run_policy_check(
        fixtures_root().join("dockerfile_enforcing/input.Dockerfile"),
        references_root().join("policy-dockerfile-enforcing.yaml"),
    );
    assert_eq!(status.code(), Some(2));
}

#[test]
fn policy_check_returns_exit_code_0_when_blocked_violations_are_absent() {
    let status = run_policy_check(
        fixtures_root().join("dockerfile_balanced/input.Dockerfile"),
        references_root().join("policy-dockerfile-balanced.yaml"),
    );
    assert_eq!(status.code(), Some(0));
}
