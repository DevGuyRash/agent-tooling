---
name: docker-architect
description: >-
  Generate hardened, production-ready Docker architecture including Dockerfiles,
  Compose stacks, and Swarm deploy configs. Use when the task involves:
  (1) Writing or improving a Dockerfile or multi-stage build, (2) Containerizing
  an application (Python, Node.js, Rust, Go, Nginx, or custom stacks),
  (3) Creating or modifying compose.yaml or Docker Swarm deployments,
  (4) Hardening container security (non-root users, read-only filesystems,
  resource limits, secrets management), (5) Adding healthchecks to containers,
  (6) Setting up CI/CD container scanning with hadolint, trivy, or docker scout,
  (7) Configuring .dockerignore files, (8) Implementing image supply-chain
  controls (digest-pinned images, OCI labels, SBOM, provenance), or (9) Any task
  involving Docker, containers, or container orchestration.
license: MIT
metadata:
  author: agent-skills
  version: "2.0.0"
compatibility: >-
  POSIX shell required. Optional: Rust/cargo (for deterministic tooling), docker,
  docker compose, jq, hadolint, trivy. Launchers at
  `<skills-file-root>/scripts/docker-architect-compose`,
  `<skills-file-root>/scripts/docker-architect-image`,
  `<skills-file-root>/scripts/docker-architect-ci-gate`.
---

# Docker Architect

Generate hardened, production-ready Docker architecture across two workflows:

- **Compose/Swarm** — service topology, runtime hardening, secrets, healthchecks
- **Image/Build** — Dockerfile, Buildx/Bake, SBOM/provenance/signing

---

## When to use this skill

Activate this skill when the user asks to:

- Write a Dockerfile or containerize an application
- Create a compose.yaml or Compose stack
- Set up a Docker Swarm deployment
- Harden or secure an existing Dockerfile or compose file
- Add healthchecks to containers
- Configure Docker secrets management
- Create a `.dockerignore` file
- Set up multi-stage Docker builds
- Add resource limits or security constraints to containers
- Configure non-root container users
- Set up a CI/CD pipeline for Docker builds
- Scan Docker images for vulnerabilities
- Pin Docker image versions or digests
- Create init containers or permission sidecars
- Optimize Docker layer caching or image size

---

## Primary Directives

The executor shall follow these rules for every output.

### 1. Clarification and defaults

- Ask the user at most **2 clarifying questions** before generating output.
- When requirements are ambiguous, apply secure defaults and note assumptions inline.
- Default workflow: if the user mentions "docker-compose" or "deploy", use Compose.
  If the user mentions "Dockerfile" or "build", use Image. When both apply, emit both.

### 2. Dockerfile invariants

Every generated Dockerfile shall satisfy:

| #  | Rule ID            | Requirement |
|----|--------------------|-------------|
| 1  | AC-DF-MULTISTAGE   | Use multi-stage builds; isolate build deps from runtime. |
| 2  | AC-DF-USER         | Final stage runs as non-root (`USER` instruction). |
| 3  | (behavioral)       | Use minimal base images (`-slim`, `-alpine`, distroless). |
| 4  | AC-DF-FROM-DIGEST  | Pin base images by digest in production (tag acceptable for templates). |
| 5  | AC-DF-HEALTHCHECK  | Include `HEALTHCHECK` in final stage. |
| 6  | AC-DF-OCI-LABELS   | Include OCI labels: `image.source`, `image.revision`, `image.licenses`. |
| 7  | AC-DF-CACHE-MOUNTS | Use BuildKit `--mount=type=cache` for package managers. |
| 8  | AC-DF-SUID-SGID    | Strip SUID/SGID bits in final stage (enforcing only). |
| 9  | (behavioral)       | Never embed secrets in layers (use build secrets or runtime mounts). |
| 10 | AC-DF-DOCKERIGNORE | Emit a companion `.dockerignore` file. |
| 11 | AC-DF-REPRODUCIBLE | Declare `ARG SOURCE_DATE_EPOCH` for reproducible builds. |
| 12 | AC-DF-PACKAGE-MGR  | Final stage must not invoke runtime package managers (apt, apk, pip, etc.). |
| 13 | (behavioral)       | Order layers: system deps → app deps (lockfiles) → source code. |

### 3. Compose / Swarm invariants

Every generated compose or stack file shall satisfy:

| #  | Rule ID            | Requirement |
|----|--------------------|-------------|
| 1  | AC-CMP-READONLY    | `read_only: true` — immutable root filesystem. |
| 2  | AC-CMP-CAPDROP     | `cap_drop: [ALL]` — drop all capabilities. |
| 3  | AC-CMP-NNP         | `security_opt: [no-new-privileges:true]`. |
| 4  | AC-CMP-USER        | `user:` set to non-root UID:GID. |
| 5  | AC-CMP-HEALTH      | `healthcheck:` with test, interval, timeout, retries. |
| 6  | AC-CMP-RESOURCES   | Compose: `cpus`, `mem_limit`, `pids_limit`; Swarm: `deploy.resources.limits`. |
| 7  | AC-CMP-SECRETS     | Route TOKEN/PASS/KEY values through `secrets:`, not `environment:`. |
| 8  | AC-CMP-DIGEST / AC-SWM-DIGEST | Pin service images by digest for deterministic pulls. |
| 9  | AC-CMP-RESTART     | `restart: unless-stopped` (Compose) or `deploy.restart_policy` (Swarm). |
| 10 | AC-CMP-WRITABLE    | Explicit `tmpfs:` for writable paths under read-only root. |
| 11 | AC-CMP-PERMS-INIT  | Init-permissions sidecar for non-root volume ownership (Compose only). |
| 12 | (behavioral)       | Use YAML anchors (`x-defaults: &`) for shared hardening. |
| 13 | (behavioral)       | Define explicit `networks:` (no default bridge). |
| 14 | (behavioral)       | Use `depends_on: { svc: { condition: service_healthy } }`. |
| 15 | (behavioral)       | Use `profiles:` for optional services (init, debug). |
| 16 | AC-SWM-RESTART     | Swarm: `deploy.restart_policy.condition: on-failure`. |

Rows marked `(behavioral)` are enforced by LLM output review only and are not checked by `policy-check`.

### 3.1 Migration notes

- **Behavior change:** `AC-CMP-PERMS-INIT` and `AC-CMP-RESTART` service
  exemptions match only the canonical `<service>-init-perms` suffix. Generic
  `init-*` service names are intentionally no longer exempt from `ensure_key`
  checks.

### 4. Response format

#### 4.1 Compose mode

- **Deliverables:** `architecture.md`, `compose.yaml`.
- Emit each file as a fenced code block labeled with its relative path.
- Emit order: `.dockerignore` (if applicable) → `compose.yaml`.
- Include inline comments referencing rule IDs (e.g., `# AC-CMP-USER`).
- **Required gates:** `policy-check`, `output-check`, `docker compose config -q`, `verify` (when Docker is available).
- Init-sidecar conformance is required for all `*-init-perms` services: must match the canonical contract (user `0:0`, cap_drop ALL, cap_add CHOWN+FOWNER, security_opt no-new-privileges, read_only true, network_mode none, restart no, no `profiles:` key).
- After all files, include a brief "Next steps" section with scanning commands.

#### 4.2 Swarm mode

- **Deliverables:** `architecture.md`, `docker-stack.yaml`.
- Emit each file as a fenced code block labeled with its relative path.
- Include inline comments referencing rule IDs (e.g., `# AC-SWM-RESTART`).
- **Required gates:** `policy-check`, `output-check`.
- Ownership-bootstrap section required for non-root stateful services with named volumes.
- **Prohibited patterns:** `depends_on`, init-perms sidecars, flat resource keys (`cpus`, `mem_limit`, `pids_limit`), `profiles:`.
- Use `deploy.resources.limits` for resource constraints, `deploy.restart_policy` for restart behavior.
- After all files, include a brief "Next steps" section with deploy commands.

#### 4.3 Image mode

- **Deliverables:** `.dockerignore`, `Dockerfile`, `docker-bake.hcl`, `architecture.md`.
- Emit each file as a fenced code block labeled with its relative path.
- Emit order: `.dockerignore` → `Dockerfile` → `docker-bake.hcl`.
- Include inline comments referencing rule IDs (e.g., `# AC-DF-USER`).
- **Required gates:** `policy-check`, `output-check`.
- `docker-bake.hcl` must include `default` and `release` targets with multi-platform support.
- Release instructions must include attestation flags (`--attest type=sbom`, `--attest type=provenance,mode=max`) and signing guidance.
- After all files, include a brief "Next steps" section with build and scanning commands.

### 5. Delivery Checklist

The executor SHALL NOT report success until every condition below is met:

- Every required gate for the active mode (per sections 4.1–4.3) has passed, OR is explicitly skipped with a documented reason and residual risk statement in the architecture output.
- When a validation step is skipped because tooling is unavailable, the architecture output SHALL record the skipped step, the reason, and the residual risk (DA-PROC-3).
- When Docker is available, Compose mode SHALL treat runtime `verify` as mandatory. Skipping verify requires an explicit note in the output (DA-PROC-2).
- Ambiguous research results affecting runtime user, healthcheck, or provenance SHALL be treated as blockers requiring resolution, not soft informational notes.
- Provenance resolution SHALL distinguish source repository provenance from an exact upstream Dockerfile/build-definition path. Source repository provenance is mandatory; exact Dockerfile path SHOULD be included when deterministically discoverable.

---

## Scanning Recommendations

After generating container files, recommend the user run:

```bash
# Lint Dockerfile
hadolint Dockerfile

# Validate compose schema
docker compose config -q

# Scan for vulnerabilities (after build)
trivy image --severity HIGH,CRITICAL <image>
```

See `references/scanning.md` for full install instructions, CI pipeline ordering,
and additional tools (docker scout, trivy config scanning).

---

## Fallback Behavior

When the Rust tooling (`docker-architect-compose`, `docker-architect-image`) is
unavailable (no cargo, no pre-built binary):

1. **Never refuse output.** Generate files directly from the invariants above.
2. Use templates from `references/fallback-templates.md` as starting points.
3. Use `.dockerignore` templates from `references/dockerignore-templates.md`.
4. Apply all Dockerfile and Compose invariants manually.
5. Note in output that deterministic tooling validation was skipped.

The fallback path produces the same hardened output — the Rust tooling adds
deterministic metadata enrichment and policy enforcement, not the hardening itself.

---

## Tooling Reference

When the Rust tooling is available, use it for enhanced determinism and policy checks.

### Workflow selection

- Use `docker-architect-compose` for stack/deployment architecture (docker-compose, Swarm).
- Use `docker-architect-image` for image/build architecture (Dockerfile, Buildx/Bake).
- When both are required, run compose first, then image, preserving traceability IDs.

### Commands

```bash
# ── Compose/Swarm workflow ──
<skills-file-root>/scripts/docker-architect-compose extract <input> --format text
<skills-file-root>/scripts/docker-architect-compose refresh --cache-dir <skills-file-root>/references/cache --image nginx:1.27 --allow-scrape-fallback
<skills-file-root>/scripts/docker-architect-compose render --cache-dir <skills-file-root>/references/cache --format markdown
<skills-file-root>/scripts/docker-architect-compose check --cache-dir <skills-file-root>/references/cache --strictness balanced
<skills-file-root>/scripts/docker-architect-compose policy-check compose.yaml --policy <skills-file-root>/references/policy-compose-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode compose
<skills-file-root>/scripts/docker-architect-compose policy-plan compose.yaml --policy <skills-file-root>/references/policy-compose-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode compose
<skills-file-root>/scripts/docker-architect-compose policy-apply compose.yaml --plan patch-plan.json --output compose.hardened.yaml --mode compose
<skills-file-root>/scripts/docker-architect-compose compose-generate compose.yaml --policy <skills-file-root>/references/policy-compose-balanced.yaml --cache-dir <skills-file-root>/references/cache --output compose.anchored.yaml --mode compose --anchors auto
<skills-file-root>/scripts/docker-architect-compose output-check architecture.md --mode compose

# ── Swarm workflow ──
<skills-file-root>/scripts/docker-architect-compose policy-check docker-stack.yaml --policy <skills-file-root>/references/policy-swarm-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode swarm
<skills-file-root>/scripts/docker-architect-compose policy-plan docker-stack.yaml --policy <skills-file-root>/references/policy-swarm-balanced.yaml --cache-dir <skills-file-root>/references/cache --mode swarm
# policy-apply currently supports only --mode compose (compose workflow) and --mode dockerfile (image workflow).
<skills-file-root>/scripts/docker-architect-compose compose-generate docker-stack.yaml --policy <skills-file-root>/references/policy-swarm-balanced.yaml --cache-dir <skills-file-root>/references/cache --output docker-stack.anchored.yaml --mode swarm --anchors auto

# ── Image/build workflow ──
<skills-file-root>/scripts/docker-architect-image extract <input> --format text
<skills-file-root>/scripts/docker-architect-image refresh --cache-dir <skills-file-root>/references/cache --image debian:12-slim --allow-scrape-fallback
<skills-file-root>/scripts/docker-architect-image render --cache-dir <skills-file-root>/references/cache --format markdown
<skills-file-root>/scripts/docker-architect-image check --cache-dir <skills-file-root>/references/cache --strictness balanced
<skills-file-root>/scripts/docker-architect-image policy-check Dockerfile --policy <skills-file-root>/references/policy-dockerfile-balanced.yaml
# policy-check exits 2 when blocked violations are present.
<skills-file-root>/scripts/docker-architect-image policy-plan Dockerfile --policy <skills-file-root>/references/policy-dockerfile-balanced.yaml
# policy-plan is non-gating and always reports to stdout.
<skills-file-root>/scripts/docker-architect-image policy-apply Dockerfile --plan patch-plan.json --output Dockerfile.hardened --mode dockerfile
<skills-file-root>/scripts/docker-architect-image output-check architecture.md --mode image

# ── CI gate ──
<skills-file-root>/scripts/docker-architect-ci-gate
DOCKER_ARCHITECT_ENABLE_VERIFY=1 <skills-file-root>/scripts/docker-architect-ci-gate
```

### Portability contract

- This skill resolves all paths within `<skills-file-root>`.
- Cross-skill runtime path dependencies are non-compliant.

### Determinism and hardening

- Refresh metadata only in explicit `refresh` operations.
- Render from cached JSON for normal runs.
- Prefer official APIs; use scrape fallback only when missing fields block output quality.
- For Docker Hub images, prefer registry v2 `Docker-Content-Digest` over Hub tag digest.
- Input guardrails: policy packs, image lists, and patch plans are capped at 1 MiB; general text inputs are capped at 8 MiB.
- Curated defaults: `references/image-knowledge/knowledge.v1.yaml`, `references/compose-defaults/defaults.v1.yaml`.

### CI gate

- `docker-architect-ci-gate` runs deterministic fixture-based golden tests.
- Live verify is opt-in via `DOCKER_ARCHITECT_ENABLE_VERIFY=1`.
- Live verify defaults to `references/ci/verify.compose.yaml`.

---

## References

| File | Purpose |
|------|---------|
| `references/fallback-templates.md` | Hardened Dockerfile + Compose templates |
| `references/fallback-templates-swarm.md` | Hardened Swarm stack template |
| `references/fallback-templates-bake.md` | docker-bake.hcl template (Image mode) |
| `references/dockerignore-templates.md` | .dockerignore templates by language |
| `references/scanning.md` | Scanner install, usage, CI pipeline order |
| `references/protocol-compose.md` | Compose workflow protocol |
| `references/protocol-swarm.md` | Swarm workflow protocol |
| `references/output-contract-compose.md` | Compose output contract |
| `references/output-contract-swarm.md` | Swarm output contract |
| `references/protocol-image.md` | Image workflow protocol |
| `references/output-contract-image.md` | Image output contract |
| `references/cache/image-profiles.json` | Cached image metadata |
| `references/policy-compose-balanced.yaml` | Compose policy (balanced) |
| `references/policy-compose-enforcing.yaml` | Compose policy (enforcing) |
| `references/policy-swarm-balanced.yaml` | Swarm policy (balanced) |
| `references/policy-swarm-enforcing.yaml` | Swarm policy (enforcing) |
| `references/policy-dockerfile-balanced.yaml` | Dockerfile policy (balanced) |
| `references/policy-dockerfile-enforcing.yaml` | Dockerfile policy (enforcing) |
| `references/compose-defaults/defaults.v1.yaml` | Compose anchor defaults |
| `references/image-knowledge/knowledge.v1.yaml` | Image knowledge base |
| `references/ci/verify.compose.yaml` | CI verify fixture |
| `references/ci/verify-stateful.compose.yaml` | CI stateful verify fixture |
