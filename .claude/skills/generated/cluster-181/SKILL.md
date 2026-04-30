---
name: cluster-181
description: "Skill for the Cluster_181 area of agent-skills. 18 symbols across 1 files."
---

# Cluster_181

18 symbols | 1 files | Cohesion: 81%

## When to Use

- Working with code in `crates/`
- Understanding how suggest_anchors, render_markdown_report work
- Modifying cluster_181-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/anchor_suggest.rs` | suggest_anchors, render_markdown_report, adaptive_threshold, compute_composite_confidence, risk_rank (+13) |

## Entry Points

Start here when exploring this area:

- **`suggest_anchors`** (Function) — `crates/architect-core/src/anchor_suggest.rs:213`
- **`render_markdown_report`** (Function) — `crates/architect-core/src/anchor_suggest.rs:684`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `suggest_anchors` | Function | `crates/architect-core/src/anchor_suggest.rs` | 213 |
| `render_markdown_report` | Function | `crates/architect-core/src/anchor_suggest.rs` | 684 |
| `adaptive_threshold` | Function | `crates/architect-core/src/anchor_suggest.rs` | 761 |
| `compute_composite_confidence` | Function | `crates/architect-core/src/anchor_suggest.rs` | 945 |
| `risk_rank` | Function | `crates/architect-core/src/anchor_suggest.rs` | 975 |
| `kind_rank` | Function | `crates/architect-core/src/anchor_suggest.rs` | 983 |
| `confidence_key` | Function | `crates/architect-core/src/anchor_suggest.rs` | 990 |
| `last_path_segment` | Function | `crates/architect-core/src/anchor_suggest.rs` | 995 |
| `top_level_fragment_keys` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1006 |
| `suggest_anchors_detects_repeated_hardening_block` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1112 |
| `suggest_anchors_uses_adaptive_threshold_for_larger_stacks` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1142 |
| `suggest_anchors_marks_sensitive_paths_high_risk` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1166 |
| `suggest_anchors_discovers_composite_intersection` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1194 |
| `suggest_anchors_schema_version_is_v2` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1230 |
| `suggest_anchors_is_deterministic` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1250 |
| `suggest_anchors_respects_min_usage_override` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1274 |
| `suggest_anchors_respects_max_suggestions` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1296 |
| `render_markdown_report_includes_yaml_fragment` | Function | `crates/architect-core/src/anchor_suggest.rs` | 1322 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_182 | 3 calls |
| Cluster_180 | 2 calls |
| Tests | 1 calls |

## How to Explore

1. `gitnexus_context({name: "suggest_anchors"})` — see callers and callees
2. `gitnexus_query({query: "cluster_181"})` — find related execution flows
3. Read key files listed above for implementation details
