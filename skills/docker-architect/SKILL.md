---
name: docker-architect
description: Design deterministic Docker architecture outputs for both Compose/Swarm deployments and image supply-chain pipelines using strict phase ordering, traceability IDs, and hardened defaults.
compatibility: Requires a POSIX shell. Local launchers are `<skills-file-root>/scripts/docker-architect-compose` and `<skills-file-root>/scripts/docker-architect-image`.
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

Run commands from `<skills-file-root>`:

```bash
# Compose/Swarm workflow
./scripts/docker-architect-compose extract <input-file> --format text
./scripts/docker-architect-compose extract <input-file> --format json
./scripts/docker-architect-compose refresh --cache-dir ./references/cache --image nginx:1.27 --allow-scrape-fallback
./scripts/docker-architect-compose render --cache-dir ./references/cache --format markdown
./scripts/docker-architect-compose check --cache-dir ./references/cache --strictness balanced
./scripts/docker-architect-compose policy-check compose.yaml --policy ./references/policy-compose-balanced.yaml --cache-dir ./references/cache
./scripts/docker-architect-compose policy-plan compose.yaml --policy ./references/policy-compose-balanced.yaml --cache-dir ./references/cache
./scripts/docker-architect-compose policy-apply compose.yaml --plan patch-plan.json --output compose.hardened.yaml --mode compose
./scripts/docker-architect-compose output-check architecture.md --mode compose

# Image/build workflow
./scripts/docker-architect-image extract <input-file> --format text
./scripts/docker-architect-image extract <input-file> --format json
./scripts/docker-architect-image refresh --cache-dir ./references/cache --image debian:12-slim --allow-scrape-fallback
./scripts/docker-architect-image render --cache-dir ./references/cache --format markdown
./scripts/docker-architect-image check --cache-dir ./references/cache --strictness balanced
./scripts/docker-architect-image policy-check Dockerfile --policy ./references/policy-dockerfile-balanced.yaml
./scripts/docker-architect-image policy-plan Dockerfile --policy ./references/policy-dockerfile-balanced.yaml
./scripts/docker-architect-image output-check architecture.md --mode image
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

## References

- Compose protocol: `references/protocol-compose.md`
- Compose output contract: `references/output-contract-compose.md`
- Image protocol: `references/protocol-image.md`
- Image output contract: `references/output-contract-image.md`
- Cache payload file: `references/cache/image-profiles.json`
- Compose policy packs: `references/policy-compose-balanced.yaml`, `references/policy-compose-enforcing.yaml`
- Dockerfile policy packs: `references/policy-dockerfile-balanced.yaml`, `references/policy-dockerfile-enforcing.yaml`
