---
name: tests
description: "Skill for the Tests area of agent-skills. 615 symbols across 49 files."
---

# Tests

615 symbols | 49 files | Cohesion: 82%

## When to Use

- Working with code in `crates/`
- Understanding how validate_artifact_file, from_session_dir, session_dir work
- Modifying tests-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/mpcr/src/session.rs` | module_id_text, severity_text, default_review_role, module_ids_for_role, default (+67) |
| `scripts/tests/test_render_table.py` | render, test_basic, test_multirow_separators, test_single_column, test_header_override (+44) |
| `crates/mpcr/tests/v2_cli.rs` | write_route_revision_doc, session_metrics_reports_categorical_counts, header, run_cmd, parent_review_doc (+22) |
| `crates/mpcr/tests/session_recursive.rs` | json_only_session_is_mirrored_back_to_toml_on_mutation, toml_only_session_is_mirrored_back_to_json_on_mutation, divergent_json_and_toml_prefer_json_and_rewrite_toml_on_mutation, cleanup_session_preserves_shared_nonempty_scratch_root, verify_application_requires_matching_application_result (+19) |
| `crates/mpcr/tests/e2e_cli.rs` | run_ok, run_json, session_fixture, child_findings_doc, spawn_routed_worker (+19) |
| `crates/mpcr/src/fullcycle_plan.rs` | policy_refs, resolve_artifact_path, load_current_artifact, collect_parent_reopen_triggers, finding_supports_reopen (+18) |
| `skills/gitops-workflow/tests/test_security_e2e.py` | run, init_repo, stage_file, hook_path, _clip (+18) |
| `skills/skill-auditor/tests/test_spec_check.py` | make_skill, test_uppercase_slug_fails, test_slug_name_fails, test_mismatched_h1_fails, test_missing_trigger_list_warns (+18) |
| `crates/mpcr/tests/banned_family.rs` | banned_family_is_absent_in_production_code, workspace_root, resolve_scan_roots, is_ident_char, find_banned_prefix (+17) |
| `crates/mpcr/src/router.rs` | has_docs_change, modules_for_surface, detect_languages, determine_architecture, build_surface_map (+16) |

## Entry Points

Start here when exploring this area:

- **`validate_artifact_file`** (Function) — `crates/mpcr/src/validate.rs:983`
- **`from_session_dir`** (Function) — `crates/mpcr/src/session.rs:597`
- **`session_dir`** (Function) — `crates/mpcr/src/session.rs:602`
- **`load_session`** (Function) — `crates/mpcr/src/session.rs:2432`
- **`ensure_session`** (Function) — `crates/mpcr/src/session.rs:2438`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `GitOpsScriptTestCase` | Class | `skills/gitops-workflow/tests/test_ship_doctor.py` | 33 |
| `StartBranchFallbackTests` | Class | `skills/gitops-workflow/tests/test_ship_doctor.py` | 224 |
| `ShipWorkflowTests` | Class | `skills/gitops-workflow/tests/test_ship_doctor.py` | 278 |
| `MarkReadyWorkflowTests` | Class | `skills/gitops-workflow/tests/test_ship_doctor.py` | 957 |
| `DoctorWorkflowTests` | Class | `skills/gitops-workflow/tests/test_ship_doctor.py` | 1024 |
| `validate_artifact_file` | Function | `crates/mpcr/src/validate.rs` | 983 |
| `from_session_dir` | Function | `crates/mpcr/src/session.rs` | 597 |
| `session_dir` | Function | `crates/mpcr/src/session.rs` | 602 |
| `load_session` | Function | `crates/mpcr/src/session.rs` | 2432 |
| `ensure_session` | Function | `crates/mpcr/src/session.rs` | 2438 |
| `register_reviewer` | Function | `crates/mpcr/src/session.rs` | 2442 |
| `close_child_reviews` | Function | `crates/mpcr/src/session.rs` | 2645 |
| `update_review` | Function | `crates/mpcr/src/session.rs` | 2681 |
| `append_reviewer_note` | Function | `crates/mpcr/src/session.rs` | 2714 |
| `append_applicator_note` | Function | `crates/mpcr/src/session.rs` | 2736 |
| `review_matches_worker_plan` | Function | `crates/mpcr/src/session.rs` | 2923 |
| `finalize_review` | Function | `crates/mpcr/src/session.rs` | 3110 |
| `set_applicator_status` | Function | `crates/mpcr/src/session.rs` | 3145 |
| `applicator_wait` | Function | `crates/mpcr/src/session.rs` | 3155 |
| `finalize_application` | Function | `crates/mpcr/src/session.rs` | 3164 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Dir_name` | cross_community | 7 |
| `Run → Legacy_lock_paths` | cross_community | 6 |
| `Soft_validation_warns_for_high_severity_application_disposition_metadata → Dir_name` | cross_community | 6 |
| `Soft_validation_warns_for_high_severity_application_disposition_metadata → Legacy_lock_paths` | cross_community | 6 |
| `Plan_reopens_for_failed_verification → Dir_name` | cross_community | 6 |
| `Plan_dedupes_matching_docs_reopen_triggers_across_review_and_verification → Dir_name` | cross_community | 6 |
| `Plan_reopens_for_partial_verification → Dir_name` | cross_community | 6 |
| `Hard_validation_matches_verification_result_to_historical_application_cycle → Dir_name` | cross_community | 6 |
| `Hard_validation_matches_verification_result_to_historical_application_cycle → Legacy_lock_paths` | cross_community | 6 |
| `Terminal_cleanup_is_one_shot → Dir_name` | cross_community | 6 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Assets | 10 calls |
| Cluster_94 | 9 calls |
| Validate_ | 6 calls |
| Cluster_88 | 6 calls |
| Cluster_92 | 6 calls |
| Cluster_90 | 5 calls |
| Cluster_89 | 4 calls |
| Cluster_97 | 3 calls |

## How to Explore

1. `gitnexus_context({name: "validate_artifact_file"})` — see callers and callees
2. `gitnexus_query({query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
