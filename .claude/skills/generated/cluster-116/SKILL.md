---
name: cluster-116
description: "Skill for the Cluster_116 area of agent-skills. 15 symbols across 1 files."
---

# Cluster_116

15 symbols | 1 files | Cohesion: 74%

## When to Use

- Working with code in `crates/`
- Understanding how run_line_check, check_dead_code_markers, check_todo_fixme work
- Modifying cluster_116-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/mpcr/src/analyze.rs` | run_line_check, check_dead_code_markers, check_todo_fixme, check_long_functions, check_long_lines (+10) |

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `run_line_check` | Function | `crates/mpcr/src/analyze.rs` | 200 |
| `check_dead_code_markers` | Function | `crates/mpcr/src/analyze.rs` | 309 |
| `check_todo_fixme` | Function | `crates/mpcr/src/analyze.rs` | 398 |
| `check_long_functions` | Function | `crates/mpcr/src/analyze.rs` | 433 |
| `check_long_lines` | Function | `crates/mpcr/src/analyze.rs` | 452 |
| `check_unreachable_markers` | Function | `crates/mpcr/src/analyze.rs` | 488 |
| `block_is_comment_only` | Function | `crates/mpcr/src/analyze.rs` | 802 |
| `truncate_line` | Function | `crates/mpcr/src/analyze.rs` | 933 |
| `has_rust_dead_code_allow_attribute` | Function | `crates/mpcr/src/analyze.rs` | 1263 |
| `comment_payload` | Function | `crates/mpcr/src/analyze.rs` | 1373 |
| `trim_comment_label_prefix` | Function | `crates/mpcr/src/analyze.rs` | 1385 |
| `is_payload_tag_boundary` | Function | `crates/mpcr/src/analyze.rs` | 1395 |
| `is_comment_ruler_line` | Function | `crates/mpcr/src/analyze.rs` | 1405 |
| `supports_inline_hash_comments` | Function | `crates/mpcr/src/analyze.rs` | 1426 |
| `find_comment_start` | Function | `crates/mpcr/src/analyze.rs` | 1430 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_119 | 2 calls |
| Cluster_120 | 2 calls |
| Cluster_117 | 2 calls |
| Cluster_115 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "run_line_check"})` — see callers and callees
2. `gitnexus_query({query: "cluster_116"})` — find related execution flows
3. Read key files listed above for implementation details
