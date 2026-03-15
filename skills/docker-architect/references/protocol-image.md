# Protocol Summary

1. Complete requirements and acceptance criteria before research.
2. Complete research sections (applicability, image inventory, unknown unknowns) before design.
3. Complete design and task list before emitting generated files.
4. Enforce emission gate if strictness requires unresolved unknowns to block output.
5. For `docker.io/*`, treat registry v2 `Docker-Content-Digest` as canonical; Docker Hub tag digests are informational only.
6. Prefer registry v2 config blobs as source-of-truth for runtime facts.
7. Evaluate dockerfile policy packs and produce deterministic artifacts (`policy-check`, `policy-plan`).
8. Emit `docker-bake.hcl` with `default` and `release` targets (multi-platform, SBOM, provenance) before output-check.
9. Include signing guidance and attestation flags (`cosign sign`, `--attest type=sbom`, `--attest type=provenance,mode=max`) in architecture output release section.
10. Run `output-check` against final markdown before final delivery.
11. Keep traceability IDs (`AC`, `IMG`, `RSK`, `O`) in every major section.
12. Record source repository provenance independently from an exact upstream Dockerfile/build-definition path; do not treat a generic repo URL as a Dockerfile path.

Use with `<skills-file-root>/scripts/docker-architect-image` to keep outputs deterministic across runs.
