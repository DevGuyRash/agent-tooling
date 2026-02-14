# Protocol Summary

1. Complete requirements and acceptance criteria before research.
2. Complete research sections (applicability, image inventory, unknown unknowns) before design.
3. Complete design and task list before emitting generated files.
4. Enforce emission gate if strictness requires unresolved unknowns to block output.
5. For `docker.io/*`, treat registry v2 `Docker-Content-Digest` as canonical; Docker Hub tag digests are informational only.
6. Prefer registry v2 config blobs as source-of-truth for runtime facts.
7. Evaluate dockerfile policy packs and produce deterministic artifacts (`policy-check`, `policy-plan`).
8. Run `output-check` against final markdown before final delivery.
9. Keep traceability IDs (`AC`, `IMG`, `RSK`, `O`) in every major section.

Use with `./scripts/docker-architect-image` to keep outputs deterministic across runs.
