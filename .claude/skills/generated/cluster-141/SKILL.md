---
name: cluster-141
description: "Skill for the Cluster_141 area of agent-skills. 16 symbols across 1 files."
---

# Cluster_141

16 symbols | 1 files | Cohesion: 73%

## When to Use

- Working with code in `crates/`
- Understanding how apply_compose_patch_plan work
- Modifying cluster_141-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/policy.rs` | apply_compose_patch_plan, ensure_services_mapping_mut, canonicalize_yaml, yaml_key_sort_key, parse_compose_service_path (+11) |

## Entry Points

Start here when exploring this area:

- **`apply_compose_patch_plan`** (Function) — `crates/architect-core/src/policy.rs:1279`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `apply_compose_patch_plan` | Function | `crates/architect-core/src/policy.rs` | 1279 |
| `ensure_services_mapping_mut` | Function | `crates/architect-core/src/policy.rs` | 1475 |
| `canonicalize_yaml` | Function | `crates/architect-core/src/policy.rs` | 1491 |
| `yaml_key_sort_key` | Function | `crates/architect-core/src/policy.rs` | 1515 |
| `parse_compose_service_path` | Function | `crates/architect-core/src/policy.rs` | 2723 |
| `parse_compose_service_root_path` | Function | `crates/architect-core/src/policy.rs` | 2735 |
| `parse_depends_on_service_path` | Function | `crates/architect-core/src/policy.rs` | 2746 |
| `apply_compose_patch_plan_updates_compose_yaml` | Function | `crates/architect-core/src/policy.rs` | 3550 |
| `apply_compose_patch_plan_noop_preserves_bytes` | Function | `crates/architect-core/src/policy.rs` | 3579 |
| `apply_compose_patch_plan_supports_remove` | Function | `crates/architect-core/src/policy.rs` | 3616 |
| `apply_compose_patch_plan_supports_nested_paths_and_indexes` | Function | `crates/architect-core/src/policy.rs` | 3839 |
| `apply_compose_patch_plan_supports_inject_service_and_depends_on_add` | Function | `crates/architect-core/src/policy.rs` | 3937 |
| `apply_compose_patch_plan_supports_set_root_for_volume_declarations` | Function | `crates/architect-core/src/policy.rs` | 3968 |
| `depends_on_add_converts_short_syntax_to_valid_long_syntax` | Function | `crates/architect-core/src/policy.rs` | 4635 |
| `apply_compose_patch_plan_rejects_oversized_path_index` | Function | `crates/architect-core/src/policy.rs` | 5450 |
| `apply_compose_patch_plan_rejects_dockerfile_sentinel_paths` | Function | `crates/architect-core/src/policy.rs` | 5467 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_149 | 3 calls |
| Cluster_125 | 1 calls |
| Cluster_145 | 1 calls |
| Tests | 1 calls |
| Cluster_144 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "apply_compose_patch_plan"})` — see callers and callees
2. `gitnexus_query({query: "cluster_141"})` — find related execution flows
3. Read key files listed above for implementation details
