---
name: assets
description: "Skill for the Assets area of agent-skills. 73 symbols across 7 files."
---

# Assets

73 symbols | 7 files | Cohesion: 78%

## When to Use

- Working with code in `skills/`
- Understanding how canonicalize work
- Modifying assets-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `skills/rust-development/assets/banned_family.rs` | raw_string_start, raw_string_end_len, find_top_level_attr_closing_bracket, parse_outer_attribute_at, parse_cfg_test_attribute_at (+58) |
| `skills/rust-development/assets/detect_rust_workspaces.py` | _dir_str, _validate_matrix_dir, _add_include, _literal_prefix_for_anchor, _matches_any |
| `skills/gitops-workflow/scripts/repo-governance.py` | canonicalize |
| `crates/mpcr/tests/v2_cli.rs` | route_cli_normalizes_relative_session_dirs_and_persisted_output_exposes_session_dir |
| `crates/mpcr/tests/e2e_cli.rs` | run_cmd |
| `crates/mpcr/tests/banned_family.rs` | new |
| `crates/architect-core/src/policy.rs` | resolve_companion_file_path |

## Entry Points

Start here when exploring this area:

- **`canonicalize`** (Function) — `skills/gitops-workflow/scripts/repo-governance.py:477`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `canonicalize` | Function | `skills/gitops-workflow/scripts/repo-governance.py` | 477 |
| `raw_string_start` | Function | `skills/rust-development/assets/banned_family.rs` | 348 |
| `raw_string_end_len` | Function | `skills/rust-development/assets/banned_family.rs` | 369 |
| `find_top_level_attr_closing_bracket` | Function | `skills/rust-development/assets/banned_family.rs` | 384 |
| `parse_outer_attribute_at` | Function | `skills/rust-development/assets/banned_family.rs` | 461 |
| `parse_cfg_test_attribute_at` | Function | `skills/rust-development/assets/banned_family.rs` | 500 |
| `parse_test_item_attribute_at` | Function | `skills/rust-development/assets/banned_family.rs` | 529 |
| `has_non_negated_test_token` | Function | `skills/rust-development/assets/banned_family.rs` | 563 |
| `is_cfg_test_attr` | Function | `skills/rust-development/assets/banned_family.rs` | 628 |
| `is_test_item_attr` | Function | `skills/rust-development/assets/banned_family.rs` | 635 |
| `is_tests_module_decl` | Function | `skills/rust-development/assets/banned_family.rs` | 640 |
| `brace_delta` | Function | `skills/rust-development/assets/banned_family.rs` | 657 |
| `cfg_annotated_item_state` | Function | `skills/rust-development/assets/banned_family.rs` | 675 |
| `cfg_attr_state_from_trailing` | Function | `skills/rust-development/assets/banned_family.rs` | 689 |
| `attribute_stack_start` | Function | `skills/rust-development/assets/banned_family.rs` | 698 |
| `compute_test_line_mask` | Function | `skills/rust-development/assets/banned_family.rs` | 710 |
| `cfg_test_single_line_item_does_not_mask_following_production_code` | Function | `skills/rust-development/assets/banned_family.rs` | 1211 |
| `bare_test_attribute_masks_only_annotated_item` | Function | `skills/rust-development/assets/banned_family.rs` | 1245 |
| `stacked_attributes_above_test_item_are_masked` | Function | `skills/rust-development/assets/banned_family.rs` | 1259 |
| `same_line_stacked_test_attribute_is_masked` | Function | `skills/rust-development/assets/banned_family.rs` | 1274 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Append_reviewer_note → New` | cross_community | 6 |
| `Verify_compose → New` | cross_community | 5 |
| `Banned_family_is_absent_in_production_code → Is_test_only_component` | intra_community | 5 |
| `Sync_agent_files_with_counters → New` | cross_community | 5 |
| `Load_state → New` | cross_community | 5 |
| `Create_or_load_session → New` | cross_community | 5 |
| `Fetch_image_profile_with_client → New` | cross_community | 5 |
| `Main → New` | cross_community | 5 |
| `Banned_family_is_absent_in_production_code → New` | cross_community | 4 |
| `Banned_family_is_absent_in_production_code → Canonicalize` | intra_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 3 calls |

## How to Explore

1. `gitnexus_context({name: "canonicalize"})` — see callers and callees
2. `gitnexus_query({query: "assets"})` — find related execution flows
3. Read key files listed above for implementation details
