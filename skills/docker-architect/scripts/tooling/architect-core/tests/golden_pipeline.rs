//! Golden pipeline integration tests for deterministic compose/swarm workflows.

use std::fs;
use std::path::{Path, PathBuf};

use architect_core::cache;
use architect_core::extract;
use architect_core::generator::{self, AnchorMode};
use architect_core::heuristics::DeployMode;
use architect_core::policy::{self, PolicyDomain};

#[derive(Debug, Clone)]
struct GoldenCase {
    name: &'static str,
    input: &'static str,
    cache_dir: &'static str,
    policy: &'static str,
    mode: DeployMode,
    expected_violation_substrings: &'static [&'static str],
    required_patch_ops: &'static [&'static str],
    forbidden_patch_ops: &'static [&'static str],
    expected_patch_plan: &'static str,
    expected_hardened: &'static str,
    expected_anchored: &'static str,
}

#[test]
fn compose_and_swarm_golden_pipeline_remains_deterministic() {
    for case in golden_cases() {
        run_case(&case);
    }
}

fn run_case(case: &GoldenCase) {
    let input_path = fixture_path(case.input);
    let cache_dir = fixture_path(case.cache_dir);
    let policy_path = references_path(case.policy);
    let patch_snapshot_path = fixture_path(case.expected_patch_plan);
    let hardened_snapshot_path = fixture_path(case.expected_hardened);
    let anchored_snapshot_path = fixture_path(case.expected_anchored);

    let input_content =
        fs::read_to_string(&input_path).expect("golden fixture input should be readable");
    let extracted = extract::extract_image_sets(&input_content)
        .expect("extract should parse deterministic image references");
    assert!(
        !extracted.valid.is_empty(),
        "fixture {} should contain image references",
        case.name
    );
    assert!(
        extracted.unresolved.is_empty(),
        "fixture {} should not contain unresolved image references",
        case.name
    );

    let cache_path = cache_dir.join("image-profiles.json");
    let cache_payload =
        cache::read_cache(&cache_path).expect("golden fixture cache should parse successfully");
    let policy_pack = policy::load_policy_pack(&policy_path, PolicyDomain::Compose)
        .expect("golden fixture policy should compile");

    let initial = policy::evaluate_compose_policy_with_mode(
        &input_content,
        &cache_payload,
        &policy_pack,
        case.mode,
    )
    .expect("initial policy evaluation should succeed");

    for expected in case.expected_violation_substrings {
        assert!(
            initial
                .violations
                .iter()
                .any(|violation| violation.reason.contains(expected)),
            "fixture {} expected violation containing `{}`",
            case.name,
            expected
        );
    }
    for op in case.required_patch_ops {
        assert!(
            initial.patch_plan.iter().any(|patch| patch.op == *op),
            "fixture {} expected patch op `{}`",
            case.name,
            op
        );
    }
    for op in case.forbidden_patch_ops {
        assert!(
            !initial.patch_plan.iter().any(|patch| patch.op == *op),
            "fixture {} should not include patch op `{}`",
            case.name,
            op
        );
    }

    let rendered_patch_plan =
        serde_json::to_string_pretty(&initial.patch_plan).expect("patch plan should serialize");
    let expected_patch_plan =
        fs::read_to_string(&patch_snapshot_path).expect("patch plan snapshot should be readable");
    assert_eq!(
        rendered_patch_plan.trim(),
        expected_patch_plan.trim(),
        "patch plan drift for fixture {}",
        case.name
    );

    let hardened = policy::apply_compose_patch_plan(&input_content, &initial.patch_plan, case.mode)
        .expect("compose patch application should succeed");
    let expected_hardened =
        fs::read_to_string(&hardened_snapshot_path).expect("hardened snapshot should be readable");
    assert_eq!(
        hardened.trim(),
        expected_hardened.trim(),
        "hardened compose drift for fixture {}",
        case.name
    );

    let reevaluated = policy::evaluate_compose_policy_with_mode(
        &hardened,
        &cache_payload,
        &policy_pack,
        case.mode,
    )
    .expect("policy re-evaluation should succeed");
    assert!(
        reevaluated.patch_plan.is_empty(),
        "fixture {} should be idempotent after first hardening apply",
        case.name
    );

    let anchored =
        generator::generate_anchored_compose(&hardened, case.mode, AnchorMode::Auto, None)
            .expect("compose anchor generation should succeed");
    let anchored_second =
        generator::generate_anchored_compose(&hardened, case.mode, AnchorMode::Auto, None)
            .expect("repeat anchor generation should succeed");
    assert_eq!(
        anchored, anchored_second,
        "anchor generation should be deterministic for fixture {}",
        case.name
    );

    let expected_anchored =
        fs::read_to_string(&anchored_snapshot_path).expect("anchored snapshot should be readable");
    assert_eq!(
        anchored.trim(),
        expected_anchored.trim(),
        "anchored compose drift for fixture {}",
        case.name
    );
}

fn golden_cases() -> Vec<GoldenCase> {
    vec![
        GoldenCase {
            name: "compose_dual",
            input: "tests/golden/compose_dual/input.compose.yaml",
            cache_dir: "tests/golden/compose_dual/cache",
            policy: "policy-compose-enforcing.yaml",
            mode: DeployMode::Compose,
            expected_violation_substrings: &[],
            required_patch_ops: &[],
            forbidden_patch_ops: &[],
            expected_patch_plan: "tests/golden/compose_dual/expected.patch-plan.json",
            expected_hardened: "tests/golden/compose_dual/expected.hardened.yaml",
            expected_anchored: "tests/golden/compose_dual/expected.anchored.yaml",
        },
        GoldenCase {
            name: "swarm_dual",
            input: "tests/golden/swarm_dual/input.stack.yaml",
            cache_dir: "tests/golden/swarm_dual/cache",
            policy: "policy-swarm-enforcing.yaml",
            mode: DeployMode::Swarm,
            expected_violation_substrings: &[],
            required_patch_ops: &[],
            forbidden_patch_ops: &[],
            expected_patch_plan: "tests/golden/swarm_dual/expected.patch-plan.json",
            expected_hardened: "tests/golden/swarm_dual/expected.hardened.yaml",
            expected_anchored: "tests/golden/swarm_dual/expected.anchored.yaml",
        },
        GoldenCase {
            name: "compose_init_perms_named_volume",
            input: "tests/golden/compose_init_perms_named_volume/input.compose.yaml",
            cache_dir: "tests/golden/compose_init_perms_named_volume/cache",
            policy: "policy-compose-enforcing.yaml",
            mode: DeployMode::Compose,
            expected_violation_substrings: &[
                "service runs as non-root with writable volumes; init sidecar enforces deterministic ownership",
            ],
            required_patch_ops: &["inject_service", "depends_on_add"],
            forbidden_patch_ops: &[],
            expected_patch_plan:
                "tests/golden/compose_init_perms_named_volume/expected.patch-plan.json",
            expected_hardened:
                "tests/golden/compose_init_perms_named_volume/expected.hardened.yaml",
            expected_anchored:
                "tests/golden/compose_init_perms_named_volume/expected.anchored.yaml",
        },
        GoldenCase {
            name: "compose_bind_mount_skip",
            input: "tests/golden/compose_bind_mount_skip/input.compose.yaml",
            cache_dir: "tests/golden/compose_bind_mount_skip/cache",
            policy: "policy-compose-balanced.yaml",
            mode: DeployMode::Compose,
            expected_violation_substrings: &[
                "bind mount target `/var/cache/app` detected; permission init sidecar chown is disabled by default to avoid host ownership mutation",
            ],
            required_patch_ops: &[],
            forbidden_patch_ops: &["inject_service", "depends_on_add"],
            expected_patch_plan: "tests/golden/compose_bind_mount_skip/expected.patch-plan.json",
            expected_hardened: "tests/golden/compose_bind_mount_skip/expected.hardened.yaml",
            expected_anchored: "tests/golden/compose_bind_mount_skip/expected.anchored.yaml",
        },
    ]
}

fn fixture_path(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join(relative)
}

fn references_path(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../references")
        .join(name)
}
