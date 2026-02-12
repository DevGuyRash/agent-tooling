---
name: principal-image-architecture-supply-chain-security-architect
description: Transform Docker image build requirements into deterministic Dockerfile/Buildx/Bake architecture outputs with strict phase ordering, traceability IDs (AC/IMG/RSK/O), supply-chain controls (SBOM/provenance/signing), and DHI-inspired hardening defaults. Use when the user requests secure image design, build pipeline generation, or modernization for reproducibility and attestations.
---

# Principal Image Architecture Supply Chain Security Architect

Produce deterministic image-architecture output via script-first research and rendering.

## Required workflow

1. Parse build goals, target artifacts, and environment hints.
2. Extract image references (`FROM`, `image:`) from provided files.
3. Refresh image metadata cache with API-first lookups.
4. Render image research content from cache.
5. Validate strictness before emitting generated artifacts.
6. Generate the final ordered sections and build artifacts.

Run commands from `<skills-file-root>`:

```bash
# 1) Extract refs from Dockerfiles/spec text
./scripts/piascs extract <input-file> --format text

# 2) Refresh deterministic cache
./scripts/piascs refresh --cache-dir ./references/cache --image debian:12-slim --allow-scrape-fallback

# 3) Render Section 2 image research
./scripts/piascs render --cache-dir ./references/cache --format markdown

# 4) Enforce strictness gate
./scripts/piascs check --cache-dir ./references/cache --strictness balanced
```

## Determinism policy

- Use `refresh` only when updating source-of-truth metadata.
- Render from cached JSON in all normal runs.
- Query official APIs first; use scraping fallback only when needed.
- Keep phase/order contract deterministic and traceable.

## Supply-chain and hardening policy

- Apply DHI-inspired controls by default.
- Prefer hardened bases when available.
- Emit Docker Official Image fallback and rationale when hardened variants are not used.
- Require explicit SBOM/provenance/signature guidance in generated outputs.

## References

- Protocol summary: `references/protocol.md`
- Output shape and IDs: `references/output-contract.md`
- Cache payload file: `references/cache/image-profiles.json`
