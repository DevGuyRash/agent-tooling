# Fallback Templates — Swarm Mode

Use this template when the Rust tooling is unavailable and the target deployment
is Docker Swarm. It encodes the same hardening invariants as the Compose template
but uses Swarm-native constructs (`deploy.*` keys, overlay networks, external secrets).

Replace all example digests with verified image digests from your registry before use.

---

## Stack Template (Hardened)

Anchor structure mirrors the Compose template for shared hardening, with Swarm-specific
resource and restart configuration via `deploy.*` keys.

```yaml
# ── Hardened Docker Swarm Stack Template ──
# Encodes invariants from policy-swarm-balanced.yaml / policy-swarm-enforcing.yaml
# Anchor structure matches the Compose fallback template for consistency.

# ── AC-CMP-READONLY + AC-CMP-CAPDROP + AC-CMP-NNP ──
x-hardening-core: &hardening_core
  cap_drop:
    - ALL
  read_only: true
  security_opt:
    - no-new-privileges:true

# ── AC-CMP-RESOURCES: Swarm-mode resource limits via deploy ──
x-resource-defaults-swarm: &resource_defaults_swarm
  deploy:
    resources:
      limits:
        cpus: "1.0"
        memory: 512M
      reservations:
        cpus: "0.25"
        memory: 128M

# ── AC-SWM-RESTART: Swarm restart policy ──
x-restart-policy-swarm: &restart_policy_swarm
  deploy:
    restart_policy:
      condition: on-failure
      delay: 5s
      max_attempts: 3
      window: 120s

# ── AC-SWM-UPDATE: Rolling update config ──
x-update-config-swarm: &update_config_swarm
  deploy:
    update_config:
      parallelism: 1
      delay: 10s
      failure_action: rollback
      order: start-first
    rollback_config:
      parallelism: 1
      delay: 5s

# ── AC-CMP-HEALTH: shared healthcheck defaults ──
x-healthcheck-defaults: &healthcheck_defaults
  interval: 30s
  timeout: 5s
  start_period: 10s
  retries: 3

services:
  app:
    <<: *hardening_core
    image: myapp@sha256:<replace-with-verified-digest>
    # ── AC-CMP-USER: non-root runtime ──
    user: "1000:1000"
    volumes:
      - app-data:/app/data
    # ── AC-CMP-SECRETS: sensitive values via external Swarm secrets ──
    secrets:
      - db_password
    environment:
      DB_HOST: db
      DB_NAME: myapp
    healthcheck:
      <<: *healthcheck_defaults
      test: ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
    # ── AC-CMP-WRITABLE: tmpfs for writable paths under read-only root ──
    tmpfs:
      - /tmp:rw,noexec,nosuid,nodev,size=64m
      - /run:rw,noexec,nosuid,nodev,size=16m
      - /var/run:rw,noexec,nosuid,nodev,size=16m
    networks:
      - backend
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 128M
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 120s
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
        order: start-first
      rollback_config:
        parallelism: 1
        delay: 5s
      placement:
        constraints:
          - node.role == worker  # Replace with actual placement constraints

  db:
    <<: *hardening_core
    image: postgres:16-alpine@sha256:<replace-with-verified-digest>
    user: "999:999"
    volumes:
      - db-data:/var/lib/postgresql/data
    secrets:
      - db_password
    environment:
      POSTGRES_DB: myapp
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    healthcheck:
      <<: *healthcheck_defaults
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      start_period: 40s
      retries: 10
    tmpfs:
      - /tmp:rw,noexec,nosuid,nodev,size=64m
      - /run:rw,noexec,nosuid,nodev,size=16m
      - /var/run/postgresql:rw,noexec,nosuid,nodev,size=16m,uid=999,gid=999,mode=775
    networks:
      - backend
    deploy:
      replicas: 1
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 256M
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 120s
      placement:
        constraints:
          - node.role == worker  # Replace with actual placement constraints

volumes:
  app-data:
  db-data:

secrets:
  db_password:
    external: true

networks:
  backend:
    driver: overlay
    attachable: true
```

---

## Ownership Bootstrap

Swarm does not support `depends_on` or init-sidecar startup sequencing. Instead, run
ownership bootstrap commands **before** `docker stack deploy`:

```bash
# ── Pre-deploy ownership bootstrap ──
# Run these on any Swarm manager node before the first stack deploy.
# Repeat after volume recreation or node migration.

# Create volumes (idempotent)
docker volume create app-data
docker volume create db-data

# Fix ownership for non-root app service (UID:GID 1000:1000)
docker run --rm -v app-data:/target alpine sh -c 'chown -R 1000:1000 /target'

# Fix ownership for non-root db service (UID:GID 999:999)
docker run --rm -v db-data:/target alpine sh -c 'chown -R 999:999 /target'

# Deploy the stack
docker stack deploy -c docker-stack.yaml mystack
```

---

## Usage Notes

- **No `depends_on`**: Swarm ignores `depends_on` entirely. Services start in parallel.
  Design services to tolerate dependency unavailability (retry loops, connection backoff).
- **No init sidecars**: The Compose init-sidecar pattern (`*-init-perms` with
  `condition: service_completed_successfully`) does not work in Swarm. Use the
  ownership bootstrap pattern above instead.
- **Resource limits via `deploy`**: Swarm uses `deploy.resources.limits` and
  `deploy.resources.reservations`, not the Compose v2 flat keys (`cpus`, `mem_limit`).
- **External secrets**: Swarm secrets must be created before stack deploy:
  `echo "password" | docker secret create db_password -`. The `external: true` pattern
  references pre-existing secrets.
- **Overlay networks**: All Swarm networks use `driver: overlay`. Set `attachable: true`
  to allow standalone containers to connect for debugging.
- **Rolling updates**: `update_config.failure_action: rollback` automatically reverts
  failed deployments. `order: start-first` ensures zero-downtime for stateless services.
- **Placement constraints**: Replace placeholder constraints with actual node labels
  or roles for production targeting.
- **Digest pinning**: Replace all `@sha256:<replace-with-verified-digest>` with actual
  digests before deployment.
