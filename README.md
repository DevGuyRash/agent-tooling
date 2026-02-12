# Agent Skills

This repository contains portable Agent Skills (AgentSkills open standard).

## Skills

### `code-review`

Unified code review skill with two workflows:

- Reviewer: perform adversarial code reviews using UACRP and produce a structured review report
- Applicator: apply review feedback from completed reports and track dispositions/progress

Both workflows coordinate artifacts under `.local/reports/code_reviews/{YYYY-MM-DD}/` and use a bundled `mpcr` tool for deterministic reviewer/session operations (ID generation, locking, session JSON updates, report writing).

Path: `skills/code-review/`

**Migration note:** `perform-code-review` and `apply-code-review` were consolidated into `code-review`. Update any tooling or docs that reference `skills/perform-code-review/` or `skills/apply-code-review/` to use `skills/code-review/`.

### `principal-containerization-architect`

Deterministic Compose/Swarm architecture skill for security-first deployment planning with strict output ordering and traceability IDs (`AC-*`, `IMG-*`, `RSK-*`, `O-*`).

- Script-first workflow via `skills/principal-containerization-architect/scripts/pca`
- API-first image metadata refresh with optional scraping fallback
- Cached, deterministic render/check workflow for repeatable section generation

Path: `skills/principal-containerization-architect/`

### `principal-image-architecture-supply-chain-security-architect`

Deterministic Docker image architecture skill for Dockerfile + Buildx/Bake planning with supply-chain controls (SBOM/provenance/signing) and strict traceability.

- Script-first workflow via `skills/principal-image-architecture-supply-chain-security-architect/scripts/piascs`
- API-first image inventory and digest/platform research with deterministic cache
- Strictness-gated output rendering for reproducible artifact planning

Path: `skills/principal-image-architecture-supply-chain-security-architect/`

## Container bootstrap scripts

These scripts are repo-wide (not skill-specific) and are intended for:
- AI agent runners that create a new container and then clone this repo
- CI/CD systems that reuse cached containers/workspaces

They are optional: each Rust-backed skill ships a shim that auto-builds on first run, but the scripts below make environments more deterministic by ensuring Rust is available and by prebuilding binaries up front.

- Fresh container (after clone): `scripts/setup.sh`
- Cached container (after checkout): `scripts/maintenance.sh`

Both scripts:
- Ensure `.local/reports/code_reviews/` exists (gitignored)
- Best-effort add the repo root to git `safe.directory`
- Prebuild `mpcr` in `skills/code-review/scripts/mpcr-src` (`cargo build --locked --release`)
- Prebuild `pca` in `skills/principal-containerization-architect/scripts/pca-src`
- Prebuild `piascs` in `skills/principal-image-architecture-supply-chain-security-architect/scripts/piascs-src`

Environment flags:
- `AGENT_SKILLS_SKIP_RUST=1` — skip Rust installation in `scripts/setup.sh`
- `AGENT_SKILLS_SKIP_MPCR_BUILD=1` — skip the `mpcr` prebuild step in either script
- `AGENT_SKILLS_SKIP_PCA_BUILD=1` — skip the `pca` prebuild step in either script
- `AGENT_SKILLS_SKIP_PIASCS_BUILD=1` — skip the `piascs` prebuild step in either script
