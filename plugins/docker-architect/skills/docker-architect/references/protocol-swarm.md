# Protocol Summary — Swarm Mode

Swarm-specific workflow. Follow these phases in order.

## Phase 0: Requirements Capture

Same as Compose protocol Phase 0. Collect user requirements, acceptance criteria,
and traceability IDs (AC-*, IMG-*, RSK-*, O-*).

## Phase 1: Research

Execute image research with Swarm-specific awareness:

- `depends_on` is **not available** in Swarm — do not emit or rely on it.
- Init-sidecar startup sequencing is **Compose-only** — do not include `*-init-perms`
  services in stack files.
- Flat resource keys (`cpus`, `mem_limit`, `pids_limit`) are **Compose-only** — use
  `deploy.resources.limits` and `deploy.resources.reservations` instead.
- Flag any research result that relies on Compose-only patterns as inapplicable.

## Phase 2: Stack Planning

- Plan the stack topology using overlay networks.
- For non-root stateful services, include an **Ownership Bootstrap** section that
  documents the pre-deploy `docker run --rm` chown pattern for each named volume.
- Define `deploy.restart_policy`, `deploy.update_config`, and `deploy.rollback_config`
  for every service.
- Placement constraint placeholders for production node targeting.

## Phase 3: Image Classification

Classify unresolved image references. In enforcing mode, block stack emission when
unresolved references remain.

## Phase 4: Policy Evaluation

Evaluate swarm policy packs:
- Balanced: `policy-swarm-balanced.yaml`
- Enforcing: `policy-swarm-enforcing.yaml`

Produce `policy-check` and `policy-plan` artifacts. Apply approved plans.

## Phase 5: Stack Emission

Emit `docker-stack.yaml` only after all prior gates pass. Use `deploy.resources.limits`
for resource constraints, `deploy.restart_policy` for restart behavior, and explicit
overlay networks.

## Phase 6: Output Validation

Run `output-check` against final markdown:

```bash
<skills-file-root>/scripts/docker-architect-compose output-check architecture.md --mode swarm
```

## Phase 7: Delivery

Include traceability IDs (AC-*, IMG-*, RSK-*, O-*) in every major section.

## Explicit Prohibitions

The following patterns are **forbidden** in Swarm stack files:

| Pattern | Reason |
|---------|--------|
| `depends_on` | Not supported by Docker Swarm |
| `*-init-perms` sidecar services | Compose-only startup sequencing |
| Flat resource keys (`cpus`, `mem_limit`, `pids_limit`) | Compose v2 only; Swarm uses `deploy.resources` |
| `profiles:` | Not supported by Docker Swarm |
| `network_mode: none` | Not compatible with Swarm overlay networking |

## Ownership Bootstrap Pattern

For non-root stateful services that need writable named volumes, document and require
a pre-deploy step:

```bash
# Run before `docker stack deploy` for each volume needing ownership repair
docker volume create <volume-name>
docker run --rm -v <volume-name>:/target alpine sh -c 'chown -R <uid>:<gid> /target'
```

This replaces the Compose-mode init-sidecar pattern.

Use this with `<skills-file-root>/scripts/docker-architect-compose` outputs to keep sections deterministic.
