---
name: cluster-143
description: "Skill for the Cluster_143 area of agent-skills. 22 symbols across 2 files."
---

# Cluster_143

22 symbols | 2 files | Cohesion: 71%

## When to Use

- Working with code in `crates/`
- Understanding how ensure_capability_profile, ensure_resource_limits work
- Modifying cluster_143-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/policy.rs` | evaluate_rule_for_service, add_compose_violation, is_init_permissions_service_name, validate_existing_init_sidecar, service_depends_on_init_sidecar (+12) |
| `crates/architect-core/src/heuristics.rs` | ensure_capability_profile, ensure_resource_limits, binds_low_port, port_mapping_contains_low_port, has_key_path |

## Entry Points

Start here when exploring this area:

- **`ensure_capability_profile`** (Function) — `crates/architect-core/src/heuristics.rs:289`
- **`ensure_resource_limits`** (Function) — `crates/architect-core/src/heuristics.rs:353`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ensure_capability_profile` | Function | `crates/architect-core/src/heuristics.rs` | 289 |
| `ensure_resource_limits` | Function | `crates/architect-core/src/heuristics.rs` | 353 |
| `evaluate_rule_for_service` | Function | `crates/architect-core/src/policy.rs` | 1601 |
| `add_compose_violation` | Function | `crates/architect-core/src/policy.rs` | 1996 |
| `is_init_permissions_service_name` | Function | `crates/architect-core/src/policy.rs` | 2011 |
| `validate_existing_init_sidecar` | Function | `crates/architect-core/src/policy.rs` | 2075 |
| `service_depends_on_init_sidecar` | Function | `crates/architect-core/src/policy.rs` | 2161 |
| `yaml_to_json` | Function | `crates/architect-core/src/policy.rs` | 2277 |
| `yaml_list_contains` | Function | `crates/architect-core/src/policy.rs` | 2283 |
| `collect_sensitive_env_keys` | Function | `crates/architect-core/src/policy.rs` | 2302 |
| `collect_declared_secret_sources` | Function | `crates/architect-core/src/policy.rs` | 2339 |
| `insert_normalized_secret_name` | Function | `crates/architect-core/src/policy.rs` | 2374 |
| `is_sensitive_env_key` | Function | `crates/architect-core/src/policy.rs` | 2381 |
| `secret_name_for_env_key` | Function | `crates/architect-core/src/policy.rs` | 2411 |
| `has_valid_digest_pin` | Function | `crates/architect-core/src/policy.rs` | 2444 |
| `is_valid_sha256_digest` | Function | `crates/architect-core/src/policy.rs` | 2450 |
| `pin_image_with_digest` | Function | `crates/architect-core/src/policy.rs` | 2459 |
| `lookup_digest_for_image` | Function | `crates/architect-core/src/policy.rs` | 2464 |
| `pin_from_instruction_arguments` | Function | `crates/architect-core/src/policy.rs` | 2617 |
| `binds_low_port` | Function | `crates/architect-core/src/heuristics.rs` | 777 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Evaluate_rule_for_service → Is_disallowed_ipv4` | cross_community | 7 |
| `Evaluate_rule_for_service → Is_disallowed_ipv6` | cross_community | 7 |
| `Evaluate_rule_for_service → Validate_image_reference_chars` | cross_community | 5 |
| `Evaluate_rule_for_service → As_str` | cross_community | 5 |
| `Evaluate_rule_for_service → Split_tag` | cross_community | 5 |
| `Evaluate_rule_for_service → Get_yaml_path` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 3 calls |
| Cluster_147 | 2 calls |
| Cluster_139 | 2 calls |
| Cluster_159 | 2 calls |
| Cluster_144 | 2 calls |
| Cluster_145 | 1 calls |
| Cluster_146 | 1 calls |
| Cluster_151 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "ensure_capability_profile"})` — see callers and callees
2. `gitnexus_query({query: "cluster_143"})` — find related execution flows
3. Read key files listed above for implementation details
