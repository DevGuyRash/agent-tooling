---
name: cluster-113
description: "Skill for the Cluster_113 area of agent-skills. 35 symbols across 1 files."
---

# Cluster_113

35 symbols | 1 files | Cohesion: 88%

## When to Use

- Working with code in `crates/`
- Understanding how run_all work
- Modifying cluster_113-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/mpcr/src/analyze.rs` | run_all, dead_code_marker_detection, dead_code_marker_detection_handles_grouped_allow_attributes, dead_code_marker_detection_handles_cfg_attr_allow_dead_code, todo_detection (+30) |

## Entry Points

Start here when exploring this area:

- **`run_all`** (Function) — `crates/mpcr/src/analyze.rs:123`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `run_all` | Function | `crates/mpcr/src/analyze.rs` | 123 |
| `dead_code_marker_detection` | Function | `crates/mpcr/src/analyze.rs` | 1507 |
| `dead_code_marker_detection_handles_grouped_allow_attributes` | Function | `crates/mpcr/src/analyze.rs` | 1524 |
| `dead_code_marker_detection_handles_cfg_attr_allow_dead_code` | Function | `crates/mpcr/src/analyze.rs` | 1544 |
| `todo_detection` | Function | `crates/mpcr/src/analyze.rs` | 1562 |
| `unreachable_detection` | Function | `crates/mpcr/src/analyze.rs` | 1576 |
| `duplicate_block_detection` | Function | `crates/mpcr/src/analyze.rs` | 1593 |
| `duplicate_blocks_require_distinct_files` | Function | `crates/mpcr/src/analyze.rs` | 1606 |
| `dead_code_marker_in_string_literal_is_ignored` | Function | `crates/mpcr/src/analyze.rs` | 1639 |
| `dead_code_marker_in_single_quoted_literal_is_ignored` | Function | `crates/mpcr/src/analyze.rs` | 1656 |
| `grouped_dead_code_marker_in_string_literal_is_ignored` | Function | `crates/mpcr/src/analyze.rs` | 1673 |
| `dead_code_marker_ignores_deprecation_comments` | Function | `crates/mpcr/src/analyze.rs` | 1691 |
| `dead_code_marker_ignores_docstring_markers` | Function | `crates/mpcr/src/analyze.rs` | 1709 |
| `unreachable_marker_in_single_quoted_literal_is_ignored` | Function | `crates/mpcr/src/analyze.rs` | 1728 |
| `analysis_skips_lockfiles_and_vendor_paths` | Function | `crates/mpcr/src/analyze.rs` | 1939 |
| `analysis_skips_generated_files` | Function | `crates/mpcr/src/analyze.rs` | 1969 |
| `analysis_skips_minified_assets` | Function | `crates/mpcr/src/analyze.rs` | 1982 |
| `marker_detection_handles_mixed_quoted_and_unquoted_occurrences` | Function | `crates/mpcr/src/analyze.rs` | 2263 |
| `marker_detection_handles_single_quoted_and_unquoted_occurrences` | Function | `crates/mpcr/src/analyze.rs` | 2281 |
| `marker_detection_ignores_inline_comment_markers` | Function | `crates/mpcr/src/analyze.rs` | 2299 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_116 | 5 calls |
| Cluster_115 | 3 calls |

## How to Explore

1. `gitnexus_context({name: "run_all"})` — see callers and callees
2. `gitnexus_query({query: "cluster_113"})` — find related execution flows
3. Read key files listed above for implementation details
