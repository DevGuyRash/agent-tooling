---
name: cluster-99
description: "Skill for the Cluster_99 area of agent-skills. 19 symbols across 1 files."
---

# Cluster_99

19 symbols | 1 files | Cohesion: 94%

## When to Use

- Working with code in `crates/`
- Understanding how render_artifact_markdown work
- Modifying cluster_99-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/mpcr/src/render.rs` | push_header, push_string_list, push_surface_summary, push_findings, push_defended_checks (+14) |

## Entry Points

Start here when exploring this area:

- **`render_artifact_markdown`** (Function) — `crates/mpcr/src/render.rs:393`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `render_artifact_markdown` | Function | `crates/mpcr/src/render.rs` | 393 |
| `push_header` | Function | `crates/mpcr/src/render.rs` | 9 |
| `push_string_list` | Function | `crates/mpcr/src/render.rs` | 24 |
| `push_surface_summary` | Function | `crates/mpcr/src/render.rs` | 36 |
| `push_findings` | Function | `crates/mpcr/src/render.rs` | 56 |
| `push_defended_checks` | Function | `crates/mpcr/src/render.rs` | 83 |
| `push_residual_risks` | Function | `crates/mpcr/src/render.rs` | 98 |
| `push_coverage` | Function | `crates/mpcr/src/render.rs` | 113 |
| `render_parent_review` | Function | `crates/mpcr/src/render.rs` | 155 |
| `render_application_result` | Function | `crates/mpcr/src/render.rs` | 189 |
| `push_verification_items` | Function | `crates/mpcr/src/render.rs` | 239 |
| `render_verification_result` | Function | `crates/mpcr/src/render.rs` | 259 |
| `render_route_decision` | Function | `crates/mpcr/src/render.rs` | 269 |
| `render_surface_map` | Function | `crates/mpcr/src/render.rs` | 293 |
| `render_child_findings` | Function | `crates/mpcr/src/render.rs` | 322 |
| `render_convergence_state` | Function | `crates/mpcr/src/render.rs` | 337 |
| `render_route_revision` | Function | `crates/mpcr/src/render.rs` | 374 |
| `header` | Function | `crates/mpcr/src/render.rs` | 416 |
| `parent_review_render_is_deterministic` | Function | `crates/mpcr/src/render.rs` | 436 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Parent_review_render_is_deterministic → Validate_compact_id` | cross_community | 5 |
| `Parent_review_render_is_deterministic → Validate_artifact_id` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 1 calls |

## How to Explore

1. `gitnexus_context({name: "render_artifact_markdown"})` — see callers and callees
2. `gitnexus_query({query: "cluster_99"})` — find related execution flows
3. Read key files listed above for implementation details
