---
name: cluster-177
description: "Skill for the Cluster_177 area of agent-skills. 19 symbols across 1 files."
---

# Cluster_177

19 symbols | 1 files | Cohesion: 97%

## When to Use

- Working with code in `crates/`
- Understanding how validate_cache work
- Modifying cluster_177-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/check.rs` | validate_cache, is_docker_hub_image, healthcheck_is_unresolved, healthcheck_resolution_is_required, provenance_is_ambiguous (+14) |

## Entry Points

Start here when exploring this area:

- **`validate_cache`** (Function) — `crates/architect-core/src/check.rs:31`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `validate_cache` | Function | `crates/architect-core/src/check.rs` | 31 |
| `is_docker_hub_image` | Function | `crates/architect-core/src/check.rs` | 122 |
| `healthcheck_is_unresolved` | Function | `crates/architect-core/src/check.rs` | 142 |
| `healthcheck_resolution_is_required` | Function | `crates/architect-core/src/check.rs` | 148 |
| `provenance_is_ambiguous` | Function | `crates/architect-core/src/check.rs` | 152 |
| `base_profile` | Function | `crates/architect-core/src/check.rs` | 168 |
| `balanced_rejects_missing_docs_for_docker_hub_image` | Function | `crates/architect-core/src/check.rs` | 196 |
| `balanced_warns_but_allows_missing_dockerfile_when_provenance_is_resolved` | Function | `crates/architect-core/src/check.rs` | 213 |
| `balanced_allows_missing_docs_for_non_docker_hub_image` | Function | `crates/architect-core/src/check.rs` | 230 |
| `balanced_rejects_missing_digest_for_non_docker_hub_image` | Function | `crates/architect-core/src/check.rs` | 244 |
| `balanced_rejects_missing_runtime_user_for_docker_hub_image` | Function | `crates/architect-core/src/check.rs` | 261 |
| `balanced_rejects_when_runtime_identity_is_fully_unresolved` | Function | `crates/architect-core/src/check.rs` | 277 |
| `balanced_rejects_ambiguous_provenance` | Function | `crates/architect-core/src/check.rs` | 295 |
| `balanced_rejects_missing_healthcheck_metadata` | Function | `crates/architect-core/src/check.rs` | 314 |
| `balanced_allows_helper_image_without_runtime_identity` | Function | `crates/architect-core/src/check.rs` | 333 |
| `balanced_rejects_gid_only_runtime_identity_hint` | Function | `crates/architect-core/src/check.rs` | 350 |
| `balanced_allows_uid_only_runtime_identity_hint` | Function | `crates/architect-core/src/check.rs` | 370 |
| `balanced_treats_unknown_runtime_user_as_unresolved` | Function | `crates/architect-core/src/check.rs` | 387 |
| `enforcing_rejects_unresolved_references` | Function | `crates/architect-core/src/check.rs` | 407 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_146 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "validate_cache"})` — see callers and callees
2. `gitnexus_query({query: "cluster_177"})` — find related execution flows
3. Read key files listed above for implementation details
