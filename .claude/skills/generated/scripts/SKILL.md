---
name: scripts
description: "Skill for the Scripts area of agent-skills. 141 symbols across 11 files."
---

# Scripts

141 symbols | 11 files | Cohesion: 88%

## When to Use

- Working with code in `skills/`
- Understanding how load_config, host_platform_id, run work
- Modifying scripts-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `scripts/package_skills.py` | load_config, host_platform_id, run, docker_available, dist_build_mode (+39) |
| `skills/gitops-workflow/scripts/batch-commit.py` | run, git_success, current_branch, current_upstream_ref, resolve_default_base (+31) |
| `skills/gitops-workflow/scripts/pr-readiness-report.py` | run, parse_args, infer_repo_slug, normalize_reviewer, fetch_pr_graph (+9) |
| `skills/gitops-workflow/scripts/generate-squash-message.py` | run, try_run, detect_base_ref, current_branch, infer_type_from_branch (+4) |
| `skills/gitops-workflow/scripts/receipt.py` | run, try_run, detect_default_base_ref, get_current_branch, get_merge_base (+3) |
| `skills/project-harness/scripts/validate_skill.py` | fail, read_frontmatter, has_crlf, extract_skill_root_refs, display_name_from_slug (+2) |
| `skills/gitops-workflow/scripts/generate-release-notes.py` | run, try_run, get_last_tag, iter_commits, parse_conventional (+1) |
| `skills/espanso-dynamic-forms/scripts/lint_dynamic_form_yaml.py` | _iter_yaml_list_items, _iter_layout_generator_args_blocks, parse_args, discover_yaml, lint_text (+1) |
| `skills/espanso-dynamic-forms/scripts/scaffold_dynamic_form.py` | parse_args, normalize_fields, yaml_scaffold, provider_scaffold, main |
| `skills/gitops-workflow/scripts/commit-message.py` | build_parser, validate, render, main |

## Entry Points

Start here when exploring this area:

- **`load_config`** (Function) — `scripts/package_skills.py:32`
- **`host_platform_id`** (Function) — `scripts/package_skills.py:43`
- **`run`** (Function) — `scripts/package_skills.py:99`
- **`docker_available`** (Function) — `scripts/package_skills.py:103`
- **`dist_build_mode`** (Function) — `scripts/package_skills.py:107`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `load_config` | Function | `scripts/package_skills.py` | 32 |
| `host_platform_id` | Function | `scripts/package_skills.py` | 43 |
| `run` | Function | `scripts/package_skills.py` | 99 |
| `docker_available` | Function | `scripts/package_skills.py` | 103 |
| `dist_build_mode` | Function | `scripts/package_skills.py` | 107 |
| `use_container_build` | Function | `scripts/package_skills.py` | 116 |
| `skill_platforms` | Function | `scripts/package_skills.py` | 432 |
| `selected_platforms` | Function | `scripts/package_skills.py` | 441 |
| `tracked_dist_paths` | Function | `scripts/package_skills.py` | 470 |
| `repo_dist_payload_paths` | Function | `scripts/package_skills.py` | 478 |
| `stale_dist_paths` | Function | `scripts/package_skills.py` | 489 |
| `bootstrap` | Function | `scripts/package_skills.py` | 499 |
| `stage_host` | Function | `scripts/package_skills.py` | 503 |
| `verify_host` | Function | `scripts/package_skills.py` | 513 |
| `ensure_tracked` | Function | `scripts/package_skills.py` | 530 |
| `verify_complete` | Function | `scripts/package_skills.py` | 556 |
| `artifact_source_path` | Function | `scripts/package_skills.py` | 561 |
| `compare_artifacts` | Function | `scripts/package_skills.py` | 574 |
| `sync_artifacts` | Function | `scripts/package_skills.py` | 599 |
| `smoke_launchers` | Function | `scripts/package_skills.py` | 621 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Fallback_command → Run` | cross_community | 7 |
| `Fallback_command → Output_text` | cross_community | 7 |
| `Plan_command → Run` | cross_community | 5 |
| `Main → Dist_build_mode` | intra_community | 4 |
| `Main → Docker_available` | intra_community | 4 |
| `Main → Load_config` | intra_community | 4 |
| `Main → Selected_skill_entries` | cross_community | 4 |
| `Main → Host_platform_id` | intra_community | 4 |
| `Apply_command → Run` | cross_community | 4 |
| `Main → Run` | intra_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_184 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "load_config"})` — see callers and callees
2. `gitnexus_query({query: "scripts"})` — find related execution flows
3. Read key files listed above for implementation details
