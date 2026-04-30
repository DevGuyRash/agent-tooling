---
name: cluster-136
description: "Skill for the Cluster_136 area of agent-skills. 49 symbols across 1 files."
---

# Cluster_136

49 symbols | 1 files | Cohesion: 89%

## When to Use

- Working with code in `crates/`
- Understanding how evaluate_compose_policy work
- Modifying cluster_136-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/policy.rs` | parse_policy_pack, evaluate_compose_policy, base_cache, parse_policy_pack_compiles_typed_actions, parse_policy_pack_compiles_build_arg_action (+44) |

## Entry Points

Start here when exploring this area:

- **`evaluate_compose_policy`** (Function) — `crates/architect-core/src/policy.rs:641`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `evaluate_compose_policy` | Function | `crates/architect-core/src/policy.rs` | 641 |
| `parse_policy_pack` | Function | `crates/architect-core/src/policy.rs` | 319 |
| `base_cache` | Function | `crates/architect-core/src/policy.rs` | 3121 |
| `parse_policy_pack_compiles_typed_actions` | Function | `crates/architect-core/src/policy.rs` | 3155 |
| `parse_policy_pack_compiles_build_arg_action` | Function | `crates/architect-core/src/policy.rs` | 3179 |
| `parse_policy_pack_compiles_healthcheck_and_companion_actions` | Function | `crates/architect-core/src/policy.rs` | 3199 |
| `parse_policy_pack_rejects_compose_rule_with_invalid_target` | Function | `crates/architect-core/src/policy.rs` | 3227 |
| `parse_policy_pack_rejects_dockerfile_rule_with_invalid_target` | Function | `crates/architect-core/src/policy.rs` | 3251 |
| `parse_policy_pack_rejects_action_not_supported_in_domain` | Function | `crates/architect-core/src/policy.rs` | 3273 |
| `parse_policy_pack_rejects_unsafe_label_key` | Function | `crates/architect-core/src/policy.rs` | 3296 |
| `parse_policy_pack_rejects_unsafe_build_arg_key` | Function | `crates/architect-core/src/policy.rs` | 3319 |
| `parse_policy_pack_accepts_repo_dockerfile_policy_files` | Function | `crates/architect-core/src/policy.rs` | 3341 |
| `evaluate_compose_policy_returns_sorted_violations_and_patch_plan` | Function | `crates/architect-core/src/policy.rs` | 3367 |
| `evaluate_compose_policy_forbid_key_removes_forbidden_setting` | Function | `crates/architect-core/src/policy.rs` | 3587 |
| `apply_compose_patch_plan_removes_merge_inherited_forbidden_key` | Function | `crates/architect-core/src/policy.rs` | 3636 |
| `evaluate_compose_policy_supports_nested_key_targets` | Function | `crates/architect-core/src/policy.rs` | 3674 |
| `evaluate_compose_policy_rejects_invalid_key_path` | Function | `crates/architect-core/src/policy.rs` | 3707 |
| `evaluate_compose_policy_resolves_merge_key_inherited_values` | Function | `crates/architect-core/src/policy.rs` | 3732 |
| `evaluate_compose_policy_resolves_nested_merge_key_values` | Function | `crates/architect-core/src/policy.rs` | 3778 |
| `evaluate_compose_policy_rejects_invalid_merge_key_source` | Function | `crates/architect-core/src/policy.rs` | 3813 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_135 | 3 calls |
| Cluster_141 | 2 calls |
| Tests | 2 calls |
| Cluster_139 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "evaluate_compose_policy"})` — see callers and callees
2. `gitnexus_query({query: "cluster_136"})` — find related execution flows
3. Read key files listed above for implementation details
