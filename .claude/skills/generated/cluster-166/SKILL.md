---
name: cluster-166
description: "Skill for the Cluster_166 area of agent-skills. 16 symbols across 1 files."
---

# Cluster_166

16 symbols | 1 files | Cohesion: 86%

## When to Use

- Working with code in `crates/`
- Understanding how build_blob_http_client, fetch_docker_hub_tag_metadata, fetch_registry_manifest work
- Modifying cluster_166-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/fetch.rs` | build_blob_http_client, fetch_docker_hub_tag_metadata, fetch_registry_manifest, parse_manifest_response, choose_manifest_digest_for_config (+11) |

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `build_blob_http_client` | Function | `crates/architect-core/src/fetch.rs` | 377 |
| `fetch_docker_hub_tag_metadata` | Function | `crates/architect-core/src/fetch.rs` | 432 |
| `fetch_registry_manifest` | Function | `crates/architect-core/src/fetch.rs` | 526 |
| `parse_manifest_response` | Function | `crates/architect-core/src/fetch.rs` | 547 |
| `choose_manifest_digest_for_config` | Function | `crates/architect-core/src/fetch.rs` | 612 |
| `fetch_manifest_config_digest` | Function | `crates/architect-core/src/fetch.rs` | 635 |
| `fetch_config_blob_details` | Function | `crates/architect-core/src/fetch.rs` | 668 |
| `request_registry` | Function | `crates/architect-core/src/fetch.rs` | 705 |
| `request_registry_with_auth` | Function | `crates/architect-core/src/fetch.rs` | 729 |
| `fetch_bearer_token` | Function | `crates/architect-core/src/fetch.rs` | 759 |
| `parse_auth_challenge` | Function | `crates/architect-core/src/fetch.rs` | 916 |
| `registry_api_host` | Function | `crates/architect-core/src/fetch.rs` | 1303 |
| `extract_platform_from_config_payload` | Function | `crates/architect-core/src/fetch.rs` | 1333 |
| `dedup_platforms` | Function | `crates/architect-core/src/fetch.rs` | 1598 |
| `parse_auth_challenge_accepts_case_insensitive_parameter_keys` | Function | `crates/architect-core/src/fetch.rs` | 1655 |
| `extract_platform_from_config_payload_reads_os_and_architecture` | Function | `crates/architect-core/src/fetch.rs` | 1685 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Fetch_image_profile_with_client → Platform` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_172 | 1 calls |
| Cluster_168 | 1 calls |
| Tests | 1 calls |

## How to Explore

1. `gitnexus_context({name: "build_blob_http_client"})` — see callers and callees
2. `gitnexus_query({query: "cluster_166"})` — find related execution flows
3. Read key files listed above for implementation details
