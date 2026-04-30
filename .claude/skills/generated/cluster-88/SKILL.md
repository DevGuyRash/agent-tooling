---
name: cluster-88
description: "Skill for the Cluster_88 area of agent-skills. 13 symbols across 1 files."
---

# Cluster_88

13 symbols | 1 files | Cohesion: 69%

## When to Use

- Working with code in `crates/`
- Understanding how validate_artifact_document work
- Modifying cluster_88-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/mpcr/src/validate.rs` | canonical_review_modules, validate_recursive_review_roster, validate_route_decision, validate_artifact_document, header (+8) |

## Entry Points

Start here when exploring this area:

- **`validate_artifact_document`** (Function) — `crates/mpcr/src/validate.rs:940`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `validate_artifact_document` | Function | `crates/mpcr/src/validate.rs` | 940 |
| `canonical_review_modules` | Function | `crates/mpcr/src/validate.rs` | 312 |
| `validate_recursive_review_roster` | Function | `crates/mpcr/src/validate.rs` | 318 |
| `validate_route_decision` | Function | `crates/mpcr/src/validate.rs` | 433 |
| `header` | Function | `crates/mpcr/src/validate.rs` | 1027 |
| `hard_validation_blocks_incomplete_recursive_review_route` | Function | `crates/mpcr/src/validate.rs` | 1047 |
| `hard_validation_accepts_recursive_review_roster_above_budget` | Function | `crates/mpcr/src/validate.rs` | 1075 |
| `soft_validation_warns_only` | Function | `crates/mpcr/src/validate.rs` | 1154 |
| `soft_validation_warns_for_low_signal_major_findings` | Function | `crates/mpcr/src/validate.rs` | 1186 |
| `hard_validation_rejects_application_result_mismatched_dispositions` | Function | `crates/mpcr/src/validate.rs` | 1252 |
| `hard_validation_rejects_non_direct_applicator_review_workers` | Function | `crates/mpcr/src/validate.rs` | 1702 |
| `hard_validation_accepts_direct_apply_composite_route` | Function | `crates/mpcr/src/validate.rs` | 1759 |
| `hard_validation_rejects_repo_path_traversal` | Function | `crates/mpcr/src/validate.rs` | 1803 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Hard_validation_accepts_recursive_review_roster_above_budget → Validate_compact_id` | cross_community | 5 |
| `Hard_validation_rejects_repo_path_traversal → Validate_compact_id` | cross_community | 5 |
| `Hard_validation_blocks_incomplete_recursive_review_route → Validate_compact_id` | cross_community | 5 |
| `Soft_validation_warns_only → Validate_compact_id` | cross_community | 5 |
| `Soft_validation_warns_for_low_signal_major_findings → Validate_compact_id` | cross_community | 5 |
| `Hard_validation_rejects_non_direct_applicator_review_workers → Validate_compact_id` | cross_community | 5 |
| `Hard_validation_accepts_direct_apply_composite_route → Validate_compact_id` | cross_community | 5 |
| `Hard_validation_accepts_recursive_review_roster_above_budget → Validate_artifact_id` | cross_community | 4 |
| `Hard_validation_accepts_recursive_review_roster_above_budget → Validate_created_at` | cross_community | 4 |
| `Hard_validation_accepts_recursive_review_roster_above_budget → Validate_confidence` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Validate_ | 8 calls |
| Tests | 3 calls |
| Cluster_87 | 1 calls |
| Cluster_89 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "validate_artifact_document"})` — see callers and callees
2. `gitnexus_query({query: "cluster_88"})` — find related execution flows
3. Read key files listed above for implementation details
