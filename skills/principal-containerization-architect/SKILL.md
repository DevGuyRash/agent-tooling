---
name: principal-containerization-architect
description: Transform conceptual or existing Docker Compose/Swarm deployment requirements into deterministic, security-first architecture outputs with strict phase ordering, traceability IDs (AC/IMG/RSK/O), DHI-inspired hardening defaults, and mode-aware compatibility rules. Use when the user requests Compose/Swarm stack design, migration, review, or generation with explicit operational/security controls.
---

# Principal Containerization Architect

Produce deterministic Compose/Swarm architecture output by executing a binary-first workflow.

## Required workflow

1. Parse user inputs and lock the target mode.
2. Extract image references from supplied files/text.
3. Refresh image metadata cache with API-first lookups.
4. Render image research blocks from cache.
5. Validate cache against strictness rules.
6. Generate final architecture content using the required section order.

Run commands from `<skills-file-root>`:

```bash
# Precondition: binaries are prebuilt via scripts/setup.sh or scripts/maintenance.sh.

# 1) Extract image refs from user-provided text/config
../principal-architect-tooling/target/release/pca extract <input-file> --format text

# 2) Refresh deterministic cache (official APIs first)
../principal-architect-tooling/target/release/pca refresh --cache-dir ./references/cache --image nginx:1.27 --allow-scrape-fallback

# 3) Render Section 2 content from cache
../principal-architect-tooling/target/release/pca render --cache-dir ./references/cache --format markdown

# 4) Enforce strictness gate
../principal-architect-tooling/target/release/pca check --cache-dir ./references/cache --strictness balanced
```

## Determinism policy

- Prefer cached render paths for normal runs.
- Use network only in explicit `refresh` operations.
- Prefer official APIs; allow HTML fallback only when API fields are missing.
- Keep all traceability IDs stable and explicit.

## Hardening policy

- Apply DHI-inspired controls by default.
- Prefer Docker Hardened Images when available and compatible.
- Never claim official DHI equivalence for generated stacks.
- Include standard Docker Official Image fallback when hardened variants are unavailable.

## References

- Protocol summary: `references/protocol.md`
- Output shape and IDs: `references/output-contract.md`
- Cache payload file: `references/cache/image-profiles.json`
