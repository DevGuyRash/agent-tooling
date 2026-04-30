---
name: validate-output-contract
description: "Skill for the Validate_output_contract area of agent-skills. 36 symbols across 1 files."
---

# Validate_output_contract

36 symbols | 1 files | Cohesion: 92%

## When to Use

- Working with code in `crates/`
- Understanding how validate_output_contract work
- Modifying validate_output_contract-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/output_check.rs` | validate_output_contract, validate_output_contract_accepts_well_formed_compose_sections, validate_output_contract_reports_missing_sections, validate_output_contract_ignores_headings_inside_code_fences, validate_output_contract_ignores_headings_inside_tilde_fences (+31) |

## Entry Points

Start here when exploring this area:

- **`validate_output_contract`** (Function) — `crates/architect-core/src/output_check.rs:29`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `validate_output_contract` | Function | `crates/architect-core/src/output_check.rs` | 29 |
| `validate_output_contract_accepts_well_formed_compose_sections` | Function | `crates/architect-core/src/output_check.rs` | 711 |
| `validate_output_contract_reports_missing_sections` | Function | `crates/architect-core/src/output_check.rs` | 742 |
| `validate_output_contract_ignores_headings_inside_code_fences` | Function | `crates/architect-core/src/output_check.rs` | 749 |
| `validate_output_contract_ignores_headings_inside_tilde_fences` | Function | `crates/architect-core/src/output_check.rs` | 784 |
| `validate_output_contract_accepts_hyphenated_markers` | Function | `crates/architect-core/src/output_check.rs` | 819 |
| `validate_output_contract_accepts_well_formed_swarm_sections` | Function | `crates/architect-core/src/output_check.rs` | 850 |
| `validate_output_contract_allows_stateless_swarm_without_bootstrap_section` | Function | `crates/architect-core/src/output_check.rs` | 893 |
| `validate_output_contract_requires_bootstrap_for_non_root_named_volume_swarm` | Function | `crates/architect-core/src/output_check.rs` | 933 |
| `validate_output_contract_requires_bootstrap_for_merged_non_root_named_volume_swarm` | Function | `crates/architect-core/src/output_check.rs` | 976 |
| `validate_output_contract_allows_merged_root_override_for_non_root_image` | Function | `crates/architect-core/src/output_check.rs` | 1021 |
| `validate_output_contract_enforces_bootstrap_order_for_non_root_named_volume_swarm` | Function | `crates/architect-core/src/output_check.rs` | 1065 |
| `validate_output_contract_requires_bootstrap_marker_for_non_root_named_volume_swarm` | Function | `crates/architect-core/src/output_check.rs` | 1110 |
| `validate_output_contract_requires_bootstrap_for_image_default_non_root_swarm` | Function | `crates/architect-core/src/output_check.rs` | 1155 |
| `validate_output_contract_requires_bootstrap_for_non_yaml_image_research_line` | Function | `crates/architect-core/src/output_check.rs` | 1206 |
| `validate_output_contract_requires_bootstrap_for_non_yaml_image_research_table` | Function | `crates/architect-core/src/output_check.rs` | 1248 |
| `validate_output_contract_requires_bootstrap_for_markdown_code_image_research_table` | Function | `crates/architect-core/src/output_check.rs` | 1293 |
| `validate_output_contract_requires_bootstrap_for_non_yaml_named_runtime_user_line` | Function | `crates/architect-core/src/output_check.rs` | 1338 |
| `validate_output_contract_requires_bootstrap_for_hyphenated_runtime_user_line` | Function | `crates/architect-core/src/output_check.rs` | 1380 |
| `validate_output_contract_requires_bootstrap_for_non_yaml_named_runtime_user_table` | Function | `crates/architect-core/src/output_check.rs` | 1422 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_125 | 4 calls |
| Assets | 1 calls |

## How to Explore

1. `gitnexus_context({name: "validate_output_contract"})` — see callers and callees
2. `gitnexus_query({query: "validate_output_contract"})` — find related execution flows
3. Read key files listed above for implementation details
