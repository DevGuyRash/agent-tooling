---
name: cluster-139
description: "Skill for the Cluster_139 area of agent-skills. 17 symbols across 2 files."
---

# Cluster_139

17 symbols | 2 files | Cohesion: 54%

## When to Use

- Working with code in `crates/`
- Understanding how evaluate_dockerfile_policy_with_cache, evaluate_dockerfile_policy_with_cache_and_source, has_multiple_stages work
- Modifying cluster_139-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/policy.rs` | evaluate_dockerfile_policy_with_cache, evaluate_dockerfile_policy_with_cache_and_source, has_digest_marker, is_digest_exempt_from_reference, extract_final_stage_labels (+9) |
| `crates/architect-core/src/dockerfile.rs` | has_multiple_stages, final_stage_range, final_stage_instructions_by_keyword |

## Entry Points

Start here when exploring this area:

- **`evaluate_dockerfile_policy_with_cache`** (Function) — `crates/architect-core/src/policy.rs:728`
- **`evaluate_dockerfile_policy_with_cache_and_source`** (Function) — `crates/architect-core/src/policy.rs:737`
- **`has_multiple_stages`** (Function) — `crates/architect-core/src/dockerfile.rs:77`
- **`final_stage_range`** (Function) — `crates/architect-core/src/dockerfile.rs:82`
- **`final_stage_instructions_by_keyword`** (Function) — `crates/architect-core/src/dockerfile.rs:107`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `evaluate_dockerfile_policy_with_cache` | Function | `crates/architect-core/src/policy.rs` | 728 |
| `evaluate_dockerfile_policy_with_cache_and_source` | Function | `crates/architect-core/src/policy.rs` | 737 |
| `has_multiple_stages` | Function | `crates/architect-core/src/dockerfile.rs` | 77 |
| `final_stage_range` | Function | `crates/architect-core/src/dockerfile.rs` | 82 |
| `final_stage_instructions_by_keyword` | Function | `crates/architect-core/src/dockerfile.rs` | 107 |
| `has_digest_marker` | Function | `crates/architect-core/src/policy.rs` | 2432 |
| `is_digest_exempt_from_reference` | Function | `crates/architect-core/src/policy.rs` | 2440 |
| `extract_final_stage_labels` | Function | `crates/architect-core/src/policy.rs` | 2572 |
| `has_suid_sgid_strip_in_final_stage` | Function | `crates/architect-core/src/policy.rs` | 2661 |
| `is_root_user` | Function | `crates/architect-core/src/policy.rs` | 2714 |
| `evaluate_dockerfile_policy_reports_missing_companion_file` | Function | `crates/architect-core/src/policy.rs` | 5094 |
| `evaluate_dockerfile_policy_accepts_present_companion_file` | Function | `crates/architect-core/src/policy.rs` | 5125 |
| `evaluate_dockerfile_policy_requires_companion_to_be_file` | Function | `crates/architect-core/src/policy.rs` | 5156 |
| `evaluate_dockerfile_policy_rejects_nonexistent_companion_source_path` | Function | `crates/architect-core/src/policy.rs` | 5189 |
| `evaluate_dockerfile_policy_reports_companion_when_source_path_is_unavailable` | Function | `crates/architect-core/src/policy.rs` | 5222 |
| `evaluate_dockerfile_policy_enforcing_mode_suppresses_companion_patch_without_source_path` | Function | `crates/architect-core/src/policy.rs` | 5246 |
| `evaluate_dockerfile_policy_enforcing_mode_suppresses_companion_patch_with_source_path` | Function | `crates/architect-core/src/policy.rs` | 5270 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_136 | 7 calls |
| Cluster_148 | 4 calls |
| Assets | 3 calls |
| Cluster_135 | 3 calls |
| Cluster_143 | 3 calls |
| Validate_ | 1 calls |
| Cluster_140 | 1 calls |
| Cluster_142 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "evaluate_dockerfile_policy_with_cache"})` — see callers and callees
2. `gitnexus_query({query: "cluster_139"})` — find related execution flows
3. Read key files listed above for implementation details
