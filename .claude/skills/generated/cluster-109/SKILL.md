---
name: cluster-109
description: "Skill for the Cluster_109 area of agent-skills. 18 symbols across 2 files."
---

# Cluster_109

18 symbols | 2 files | Cohesion: 93%

## When to Use

- Working with code in `crates/`
- Understanding how record_artifact, header work
- Modifying cluster_109-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/mpcr/src/metrics.rs` | increment, worker_key, module_key, surface_key, decline_key (+12) |
| `crates/mpcr/src/artifacts.rs` | header |

## Entry Points

Start here when exploring this area:

- **`record_artifact`** (Function) — `crates/mpcr/src/metrics.rs:269`
- **`header`** (Function) — `crates/mpcr/src/artifacts.rs:901`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `record_artifact` | Function | `crates/mpcr/src/metrics.rs` | 269 |
| `header` | Function | `crates/mpcr/src/artifacts.rs` | 901 |
| `increment` | Function | `crates/mpcr/src/metrics.rs` | 50 |
| `worker_key` | Function | `crates/mpcr/src/metrics.rs` | 55 |
| `module_key` | Function | `crates/mpcr/src/metrics.rs` | 62 |
| `surface_key` | Function | `crates/mpcr/src/metrics.rs` | 69 |
| `decline_key` | Function | `crates/mpcr/src/metrics.rs` | 76 |
| `duplicate_key` | Function | `crates/mpcr/src/metrics.rs` | 83 |
| `reopen_key` | Function | `crates/mpcr/src/metrics.rs` | 90 |
| `verification_key` | Function | `crates/mpcr/src/metrics.rs` | 97 |
| `producer_worker_key` | Function | `crates/mpcr/src/metrics.rs` | 104 |
| `increment_grouped_precision` | Function | `crates/mpcr/src/metrics.rs` | 128 |
| `record_child_findings` | Function | `crates/mpcr/src/metrics.rs` | 168 |
| `record_application_result` | Function | `crates/mpcr/src/metrics.rs` | 207 |
| `record_convergence_state` | Function | `crates/mpcr/src/metrics.rs` | 250 |
| `header` | Function | `crates/mpcr/src/metrics.rs` | 383 |
| `telemetry_aggregates_by_required_categories` | Function | `crates/mpcr/src/metrics.rs` | 403 |
| `decline_reasons_are_not_double_counted_and_grouped_rows_exist` | Function | `crates/mpcr/src/metrics.rs` | 443 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 2 calls |

## How to Explore

1. `gitnexus_context({name: "record_artifact"})` — see callers and callees
2. `gitnexus_query({query: "cluster_109"})` — find related execution flows
3. Read key files listed above for implementation details
