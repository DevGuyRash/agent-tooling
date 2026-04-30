---
name: evaluate-dockerfile-policy
description: "Skill for the Evaluate_dockerfile_policy area of agent-skills. 13 symbols across 1 files."
---

# Evaluate_dockerfile_policy

13 symbols | 1 files | Cohesion: 67%

## When to Use

- Working with code in `crates/`
- Understanding how evaluate_dockerfile_policy work
- Modifying evaluate_dockerfile_policy-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/policy.rs` | evaluate_dockerfile_policy, evaluate_dockerfile_policy_rejects_invalid_target_in_manual_policy_pack, evaluate_dockerfile_policy_reports_expected_violations_and_patch_ops, evaluate_dockerfile_policy_reports_unpinned_from_references, evaluate_dockerfile_policy_allows_scratch_from_without_digest (+8) |

## Entry Points

Start here when exploring this area:

- **`evaluate_dockerfile_policy`** (Function) — `crates/architect-core/src/policy.rs:720`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `evaluate_dockerfile_policy` | Function | `crates/architect-core/src/policy.rs` | 720 |
| `evaluate_dockerfile_policy_rejects_invalid_target_in_manual_policy_pack` | Function | `crates/architect-core/src/policy.rs` | 3401 |
| `evaluate_dockerfile_policy_reports_expected_violations_and_patch_ops` | Function | `crates/architect-core/src/policy.rs` | 3419 |
| `evaluate_dockerfile_policy_reports_unpinned_from_references` | Function | `crates/architect-core/src/policy.rs` | 4721 |
| `evaluate_dockerfile_policy_allows_scratch_from_without_digest` | Function | `crates/architect-core/src/policy.rs` | 4742 |
| `evaluate_dockerfile_policy_flags_invalid_from_digest_marker` | Function | `crates/architect-core/src/policy.rs` | 4761 |
| `evaluate_dockerfile_policy_reports_missing_suid_sgid_strip` | Function | `crates/architect-core/src/policy.rs` | 4894 |
| `evaluate_dockerfile_policy_accepts_portable_suid_sgid_strip_command` | Function | `crates/architect-core/src/policy.rs` | 4927 |
| `evaluate_dockerfile_policy_reports_missing_required_build_arg` | Function | `crates/architect-core/src/policy.rs` | 4956 |
| `evaluate_dockerfile_policy_accepts_legacy_ensure_arg_action_alias` | Function | `crates/architect-core/src/policy.rs` | 4985 |
| `evaluate_dockerfile_policy_accepts_existing_required_build_arg` | Function | `crates/architect-core/src/policy.rs` | 5014 |
| `evaluate_dockerfile_policy_reports_missing_healthcheck` | Function | `crates/architect-core/src/policy.rs` | 5038 |
| `evaluate_dockerfile_policy_enforcing_missing_healthcheck_has_no_placeholder_patch` | Function | `crates/architect-core/src/policy.rs` | 5066 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_136 | 11 calls |
| Cluster_139 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "evaluate_dockerfile_policy"})` — see callers and callees
2. `gitnexus_query({query: "evaluate_dockerfile_policy"})` — find related execution flows
3. Read key files listed above for implementation details
