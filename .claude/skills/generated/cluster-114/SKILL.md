---
name: cluster-114
description: "Skill for the Cluster_114 area of agent-skills. 37 symbols across 1 files."
---

# Cluster_114

37 symbols | 1 files | Cohesion: 99%

## When to Use

- Working with code in `crates/`
- Understanding how run_check work
- Modifying cluster_114-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/mpcr/src/analyze.rs` | run_check, check_output_findings, long_python_function_is_detected_without_braces, long_python_function_at_threshold_is_not_reported_on_dedent, long_function_detection_ignores_function_like_strings (+32) |

## Entry Points

Start here when exploring this area:

- **`run_check`** (Function) — `crates/mpcr/src/analyze.rs:171`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `run_check` | Function | `crates/mpcr/src/analyze.rs` | 171 |
| `check_output_findings` | Function | `crates/mpcr/src/analyze.rs` | 227 |
| `long_python_function_is_detected_without_braces` | Function | `crates/mpcr/src/analyze.rs` | 1745 |
| `long_python_function_at_threshold_is_not_reported_on_dedent` | Function | `crates/mpcr/src/analyze.rs` | 1764 |
| `long_function_detection_ignores_function_like_strings` | Function | `crates/mpcr/src/analyze.rs` | 1781 |
| `long_function_detection_ignores_function_like_python_triple_quotes` | Function | `crates/mpcr/src/analyze.rs` | 1797 |
| `run_check_supports_duplicates_with_blank_lines` | Function | `crates/mpcr/src/analyze.rs` | 1839 |
| `duplicate_check_ignores_four_line_blocks` | Function | `crates/mpcr/src/analyze.rs` | 1859 |
| `duplicate_check_ignores_comment_only_headers` | Function | `crates/mpcr/src/analyze.rs` | 1873 |
| `todo_check_ignores_descriptive_doc_comments` | Function | `crates/mpcr/src/analyze.rs` | 1894 |
| `todo_check_ignores_rust_safety_comments` | Function | `crates/mpcr/src/analyze.rs` | 1909 |
| `long_lines_ignore_comment_rulers` | Function | `crates/mpcr/src/analyze.rs` | 1924 |
| `long_function_detection_handles_new_function_on_dedent_line` | Function | `crates/mpcr/src/analyze.rs` | 1996 |
| `single_line_function_closes_before_skipped_lines` | Function | `crates/mpcr/src/analyze.rs` | 2014 |
| `run_check_supports_complexity_for_pub_async_fn` | Function | `crates/mpcr/src/analyze.rs` | 2030 |
| `function_analysis_tracks_attribute_prefixed_function_declaration` | Function | `crates/mpcr/src/analyze.rs` | 2049 |
| `long_function_detection_supports_async_python_signatures` | Function | `crates/mpcr/src/analyze.rs` | 2084 |
| `long_function_dedent_closes_before_skipped_top_level_comment_lines` | Function | `crates/mpcr/src/analyze.rs` | 2103 |
| `complexity_dedent_closes_scope_before_top_level_branches` | Function | `crates/mpcr/src/analyze.rs` | 2119 |
| `complexity_allman_style_function_tracks_brace_scoped_branches` | Function | `crates/mpcr/src/analyze.rs` | 2135 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_115 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "run_check"})` — see callers and callees
2. `gitnexus_query({query: "cluster_114"})` — find related execution flows
3. Read key files listed above for implementation details
