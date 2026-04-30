---
name: validate
description: "Skill for the Validate_ area of agent-skills. 18 symbols across 3 files."
---

# Validate_

18 symbols | 3 files | Cohesion: 65%

## When to Use

- Working with code in `crates/`
- Understanding how validate_artifact_id, validate_created_at, validate_confidence work
- Modifying validate_-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/mpcr/src/validate.rs` | validate_header, validate_repo_paths, validate_coverage, validate_artifact_refs, validate_findings (+6) |
| `crates/architect-core/src/policy.rs` | validate_rule_action_payload, validate_dockerfile_label_key, validate_dockerfile_build_arg_key, validate_companion_file_key |
| `crates/mpcr/src/artifacts.rs` | validate_artifact_id, validate_created_at, validate_confidence |

## Entry Points

Start here when exploring this area:

- **`validate_artifact_id`** (Function) — `crates/mpcr/src/artifacts.rs:1081`
- **`validate_created_at`** (Function) — `crates/mpcr/src/artifacts.rs:1096`
- **`validate_confidence`** (Function) — `crates/mpcr/src/artifacts.rs:1110`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `validate_artifact_id` | Function | `crates/mpcr/src/artifacts.rs` | 1081 |
| `validate_created_at` | Function | `crates/mpcr/src/artifacts.rs` | 1096 |
| `validate_confidence` | Function | `crates/mpcr/src/artifacts.rs` | 1110 |
| `validate_header` | Function | `crates/mpcr/src/validate.rs` | 36 |
| `validate_repo_paths` | Function | `crates/mpcr/src/validate.rs` | 53 |
| `validate_coverage` | Function | `crates/mpcr/src/validate.rs` | 61 |
| `validate_artifact_refs` | Function | `crates/mpcr/src/validate.rs` | 67 |
| `validate_findings` | Function | `crates/mpcr/src/validate.rs` | 86 |
| `validate_surface_map` | Function | `crates/mpcr/src/validate.rs` | 502 |
| `validate_child_findings` | Function | `crates/mpcr/src/validate.rs` | 529 |
| `validate_parent_review` | Function | `crates/mpcr/src/validate.rs` | 556 |
| `validate_application_result` | Function | `crates/mpcr/src/validate.rs` | 576 |
| `validate_convergence_state` | Function | `crates/mpcr/src/validate.rs` | 805 |
| `validate_route_revision` | Function | `crates/mpcr/src/validate.rs` | 836 |
| `validate_rule_action_payload` | Function | `crates/architect-core/src/policy.rs` | 534 |
| `validate_dockerfile_label_key` | Function | `crates/architect-core/src/policy.rs` | 548 |
| `validate_dockerfile_build_arg_key` | Function | `crates/architect-core/src/policy.rs` | 580 |
| `validate_companion_file_key` | Function | `crates/architect-core/src/policy.rs` | 2027 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Route_revision_reports_actual_architecture_change → Validate_artifact_id` | cross_community | 4 |
| `Route_revision_reports_actual_architecture_change → Validate_created_at` | cross_community | 4 |
| `Route_revision_reports_actual_architecture_change → Validate_confidence` | cross_community | 4 |
| `Route_revision_can_raise_rigor_and_expand_modules → Validate_artifact_id` | cross_community | 4 |
| `Route_revision_can_raise_rigor_and_expand_modules → Validate_created_at` | cross_community | 4 |
| `Route_revision_can_raise_rigor_and_expand_modules → Validate_confidence` | cross_community | 4 |
| `Hard_validation_accepts_recursive_review_roster_above_budget → Validate_artifact_id` | cross_community | 4 |
| `Hard_validation_accepts_recursive_review_roster_above_budget → Validate_created_at` | cross_community | 4 |
| `Hard_validation_accepts_recursive_review_roster_above_budget → Validate_confidence` | cross_community | 4 |
| `Hard_validation_rejects_repo_path_traversal → Validate_artifact_id` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 3 calls |
| Cluster_90 | 1 calls |
| Cluster_108 | 1 calls |
| Assets | 1 calls |

## How to Explore

1. `gitnexus_context({name: "validate_artifact_id"})` — see callers and callees
2. `gitnexus_query({query: "validate_"})` — find related execution flows
3. Read key files listed above for implementation details
