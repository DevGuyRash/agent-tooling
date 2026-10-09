# Docker, Workspaces, and Monorepos

Load this file when the repo has multiple components or Docker-assisted workflows.

## Recipe layering

For multi-component repos, prefer two layers:

- component-prefixed recipes, such as `backend-build` or `web-test`
- aggregate top-level recipes, such as `build` or `test`

The component-prefixed layer is for precision. The aggregate layer is for the everyday path.

## Bootstrap strategy

Prefer the narrowest correct bootstrap step:

- root-level bootstrap when the workspace is genuinely centralized
- component-level bootstrap when each component owns its own dependencies

## CI strategy

For workspaces and monorepos, prefer `direct` CI mode. That keeps setup and sequencing visible and makes matrices, caching, and artifacts easier to evolve.

## Docker helpers

If compose files are present, you may expose helper recipes such as:

- `docker-build`
- `docker-up`
- `docker-down`
- `docker-logs`
- `docker-clean`

These are helpers, not the whole harness. Keep the normal bootstrap/build/test lifecycle beside them unless the repo is intentionally container-first.
