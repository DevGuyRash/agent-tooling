---
name: docker-architect
description: Design deterministic Docker architecture outputs for both Compose/Swarm deployments and image supply-chain pipelines using strict phase ordering, traceability IDs, and hardened defaults.
compatibility: Requires a POSIX shell. Local launchers are `<skills-file-root>/scripts/docker-architect-compose`, `<skills-file-root>/scripts/docker-architect-image`, and `<skills-file-root>/scripts/docker-architect-ci-gate`.
---

# Docker Architect

Generate deterministic Docker architecture outputs across two workflows:

- Compose/Swarm deployment architecture (service topology and runtime hardening)
- Image/build architecture (Dockerfile, Buildx/Bake, SBOM/provenance/signing)

## Workflow selection

- Use `docker-architect-compose` when the task is mainly stack/deployment architecture (`docker-compose`, Swarm services, runtime operations).
- Use `docker-architect-image` when the task is mainly image/build architecture (`Dockerfile`, Buildx/Bake, supply-chain controls).
- When both are required, run compose workflow first, then image workflow, and preserve deterministic traceability IDs.

## Required workflow

1. Parse user inputs and lock the workflow mode.
2. Extract image references from supplied files/text and classify unresolved interpolations.
3. Refresh image metadata cache with API-first lookups (registry v2 digest is source of truth).
4. Render image research blocks from cache.
5. Validate cache against strictness rules.
6. Generate final architecture content using required section ordering.
7. Validate final markdown output contract before returning.

Use absolute skill-rooted paths:

```bash
# Compose/Swarm workflow
<skills-file-root>/scripts/docker-architect-compose extract <input-file> --format text
<skills-file-root>/scripts/docker-architect-compose extract <input-file> --format json
<skills-file-root>/scripts/docker-architect-compose refresh --cache-dir <skills-file-root>/references/cache --image nginx:1.27 --allow-scrape-fallback
<skills-file-root>/scripts/docker-architect-compose render --cache-dir <skills-file-root>/references/cache --format markdown
<skills-file-root>/scripts/docker-architect-compose check --cache-dir <skills-file-root>/references/cache --strictness balanced
<skills-file-root>/scripts/docker-architect-compose policy-check compose.yaml --policy <skills-file-root>/references/policy-compose-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode compose
<skills-file-root>/scripts/docker-architect-compose policy-plan compose.yaml --policy <skills-file-root>/references/policy-compose-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode compose
<skills-file-root>/scripts/docker-architect-compose policy-apply compose.yaml --plan patch-plan.json --output compose.hardened.yaml --mode compose
<skills-file-root>/scripts/docker-architect-compose policy-check stack.yaml --policy <skills-file-root>/references/policy-swarm-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode swarm
<skills-file-root>/scripts/docker-architect-compose policy-plan stack.yaml --policy <skills-file-root>/references/policy-swarm-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode swarm
<skills-file-root>/scripts/docker-architect-compose compose-generate compose.yaml --policy <skills-file-root>/references/policy-compose-balanced.yaml --cache-dir <skills-file-root>/references/cache --output compose.anchored.yaml --mode compose --anchors auto
<skills-file-root>/scripts/docker-architect-compose anchor-suggest compose.yaml --policy <skills-file-root>/references/policy-compose-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode compose --format json
<skills-file-root>/scripts/docker-architect-compose output-check architecture.md --mode compose

# Image/build workflow
<skills-file-root>/scripts/docker-architect-image extract <input-file> --format text
<skills-file-root>/scripts/docker-architect-image extract <input-file> --format json
<skills-file-root>/scripts/docker-architect-image refresh --cache-dir <skills-file-root>/references/cache --image debian:12-slim --allow-scrape-fallback
<skills-file-root>/scripts/docker-architect-image render --cache-dir <skills-file-root>/references/cache --format markdown
<skills-file-root>/scripts/docker-architect-image check --cache-dir <skills-file-root>/references/cache --strictness balanced
<skills-file-root>/scripts/docker-architect-image policy-check Dockerfile --policy <skills-file-root>/references/policy-dockerfile-balanced.yaml
<skills-file-root>/scripts/docker-architect-image policy-plan Dockerfile --policy <skills-file-root>/references/policy-dockerfile-balanced.yaml
<skills-file-root>/scripts/docker-architect-image output-check architecture.md --mode image

# Generalized deterministic CI gate (fixtures + optional live verify)
<skills-file-root>/scripts/docker-architect-ci-gate
DOCKER_ARCHITECT_ENABLE_VERIFY=1 <skills-file-root>/scripts/docker-architect-ci-gate
DOCKER_ARCHITECT_ENABLE_VERIFY=1 DOCKER_ARCHITECT_VERIFY_COMPOSE_FILE=<skills-file-root>/references/ci/verify.compose.yaml <skills-file-root>/scripts/docker-architect-ci-gate
```

## Portability contract

- This skill is intended to be installable and runnable from `<skills-file-root>` only.
- Runtime entrypoints and references MUST resolve within this skill folder.
- Cross-skill runtime path dependencies are non-compliant.

## Determinism and hardening

- Refresh metadata only in explicit `refresh` operations.
- Render from cached JSON for normal runs.
- Prefer official APIs; use scrape fallback only when missing fields block output quality.
- For Docker Hub images, always prefer registry v2 `Docker-Content-Digest` over Hub tag digest data.
- Apply hardened image and supply-chain controls by default.
- Curated deterministic image defaults are versioned in `references/image-knowledge/knowledge.v1.yaml`.
- Curated deterministic compose anchor defaults are versioned in `references/compose-defaults/defaults.v1.yaml`.
- Anchor suggestions are report-only and do not mutate defaults unless manually reviewed and applied.

## CI gate

- `<skills-file-root>/scripts/docker-architect-ci-gate` always runs deterministic fixture-based golden tests (`architect-core` `golden_pipeline` integration test).
- Live runtime verify is opt-in via `DOCKER_ARCHITECT_ENABLE_VERIFY=1`. If requested, Docker availability and daemon reachability are required.
- Live verify defaults to `references/ci/verify.compose.yaml`; override with `DOCKER_ARCHITECT_VERIFY_COMPOSE_FILE=<path>`.
- Runtime verify is a baseline hardening gate: it runs `docker compose up -d` and inspects current state without waiting/polling for health transitions.
- On stacks with real healthchecks, services that are still `starting` at inspection time may fail verify even if they would become healthy later.
- The verify stage runs `docker-architect-compose verify ...` and fails the gate unless report `success` is `true`.

## References

- Compose protocol: `references/protocol-compose.md`
- Compose output contract: `references/output-contract-compose.md`
- Image protocol: `references/protocol-image.md`
- Image output contract: `references/output-contract-image.md`
- Cache payload file: `references/cache/image-profiles.json`
- Compose policy packs: `references/policy-compose-balanced.yaml`, `references/policy-compose-enforcing.yaml`
- Swarm policy packs: `references/policy-swarm-balanced.yaml`, `references/policy-swarm-enforcing.yaml`
- Compose defaults: `references/compose-defaults/defaults.v1.yaml`
- Dockerfile policy packs: `references/policy-dockerfile-balanced.yaml`, `references/policy-dockerfile-enforcing.yaml`
- CI verify fixture: `references/ci/verify.compose.yaml`
