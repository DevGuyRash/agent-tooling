---
name: cluster-165
description: "Skill for the Cluster_165 area of agent-skills. 18 symbols across 1 files."
---

# Cluster_165

18 symbols | 1 files | Cohesion: 75%

## When to Use

- Working with code in `crates/`
- Understanding how fetch_image_profile, fetch_profiles work
- Modifying cluster_165-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `crates/architect-core/src/fetch.rs` | fetch_image_profile, fetch_image_profile_with_client, fetch_profiles, build_http_client, fetch_docker_hub_metadata (+13) |

## Entry Points

Start here when exploring this area:

- **`fetch_image_profile`** (Function) — `crates/architect-core/src/fetch.rs:97`
- **`fetch_profiles`** (Function) — `crates/architect-core/src/fetch.rs:349`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `fetch_image_profile` | Function | `crates/architect-core/src/fetch.rs` | 97 |
| `fetch_profiles` | Function | `crates/architect-core/src/fetch.rs` | 349 |
| `fetch_image_profile_with_client` | Function | `crates/architect-core/src/fetch.rs` | 107 |
| `build_http_client` | Function | `crates/architect-core/src/fetch.rs` | 367 |
| `fetch_docker_hub_metadata` | Function | `crates/architect-core/src/fetch.rs` | 399 |
| `fetch_docker_hub_repo_dockerfile_url` | Function | `crates/architect-core/src/fetch.rs` | 476 |
| `enrich_researched_env_from_docs` | Function | `crates/architect-core/src/fetch.rs` | 1011 |
| `fetch_docs_text` | Function | `crates/architect-core/src/fetch.rs` | 1123 |
| `build_docs_request` | Function | `crates/architect-core/src/fetch.rs` | 1142 |
| `extract_recommended_env_from_docs` | Function | `crates/architect-core/src/fetch.rs` | 1156 |
| `is_probable_env_key` | Function | `crates/architect-core/src/fetch.rs` | 1182 |
| `is_digest_reference` | Function | `crates/architect-core/src/fetch.rs` | 1310 |
| `detect_runtime_signatures` | Function | `crates/architect-core/src/fetch.rs` | 1492 |
| `stable_failure_status` | Function | `crates/architect-core/src/fetch.rs` | 1541 |
| `parse_http_status` | Function | `crates/architect-core/src/fetch.rs` | 1568 |
| `runtime_profile_has_data` | Function | `crates/architect-core/src/fetch.rs` | 1575 |
| `build_docs_request_sets_github_raw_headers` | Function | `crates/architect-core/src/fetch.rs` | 1866 |
| `extract_recommended_env_from_docs_reads_environment_table_rows` | Function | `crates/architect-core/src/fetch.rs` | 1893 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Fetch_image_profile_with_client → Parse_github_owner_repo` | cross_community | 6 |
| `Fetch_image_profile_with_client → Is_disallowed_ipv4` | cross_community | 5 |
| `Fetch_image_profile_with_client → Is_disallowed_ipv6` | cross_community | 5 |
| `Fetch_image_profile_with_client → Platform` | cross_community | 5 |
| `Fetch_image_profile_with_client → New` | cross_community | 5 |
| `Fetch_image_profile_with_client → As_str` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_166 | 3 calls |
| Cluster_167 | 2 calls |
| Cluster_170 | 2 calls |
| Cluster_157 | 1 calls |
| Cluster_171 | 1 calls |
| Assets | 1 calls |
| Tests | 1 calls |

## How to Explore

1. `gitnexus_context({name: "fetch_image_profile"})` — see callers and callees
2. `gitnexus_query({query: "cluster_165"})` — find related execution flows
3. Read key files listed above for implementation details
