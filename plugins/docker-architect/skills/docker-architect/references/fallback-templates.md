# Fallback Templates

Use these templates when the Rust tooling (`docker-architect-compose`,
`docker-architect-image`) is unavailable. They encode the same hardening invariants
enforced by the policy packs. Adapt to the user's language/framework.
Replace all example digests with verified image digests from your registry before use.

---

## Dockerfile Templates

### Python / FastAPI

```dockerfile
# ── AC-DF-MULTISTAGE: isolate build deps from runtime ──
# ── AC-DF-FROM-DIGEST: pin base images by digest ──
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111 AS builder

# ── AC-DF-REPRODUCIBLE: deterministic build metadata ──
ARG SOURCE_DATE_EPOCH=0

WORKDIR /app

# ── Layer ordering: deps before source for cache efficiency ──
COPY requirements.txt .
# ── AC-DF-CACHE-MOUNTS: BuildKit cache for pip ──
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile --prefix=/install -r requirements.txt

COPY . .

# ── Runtime stage ──
FROM python:${PYTHON_VERSION}-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111 AS runtime

# ── AC-DF-OCI-LABELS: supply-chain traceability ──
LABEL org.opencontainers.image.source="" \
      org.opencontainers.image.revision="" \
      org.opencontainers.image.licenses=""

# ── AC-DF-SUID-SGID: strip privilege escalation bits ──
RUN find / -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} + 2>/dev/null || true

# ── AC-DF-USER: non-root runtime ──
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder /app .

RUN chown -R app:app /app
USER app

EXPOSE 8000

# ── AC-DF-HEALTHCHECK: runtime health verification ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Node.js / Next.js

```dockerfile
# ── AC-DF-MULTISTAGE: isolate build deps from runtime ──
ARG NODE_VERSION=22
FROM node:${NODE_VERSION}-slim@sha256:2222222222222222222222222222222222222222222222222222222222222222 AS deps

WORKDIR /app
COPY package.json package-lock.json ./
# ── AC-DF-CACHE-MOUNTS: BuildKit cache for npm ──
RUN --mount=type=cache,target=/root/.npm \
    npm ci --ignore-scripts

FROM node:${NODE_VERSION}-slim@sha256:2222222222222222222222222222222222222222222222222222222222222222 AS builder

# ── AC-DF-REPRODUCIBLE ──
ARG SOURCE_DATE_EPOCH=0

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ── Runtime stage ──
FROM node:${NODE_VERSION}-slim@sha256:2222222222222222222222222222222222222222222222222222222222222222 AS runtime

# ── AC-DF-OCI-LABELS ──
LABEL org.opencontainers.image.source="" \
      org.opencontainers.image.revision="" \
      org.opencontainers.image.licenses=""

# ── AC-DF-SUID-SGID ──
RUN find / -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} + 2>/dev/null || true

# ── AC-DF-USER ──
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

RUN chown -R app:app /app
USER app

EXPOSE 3000

# ── AC-DF-HEALTHCHECK ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/api/health', r => { process.exit(r.statusCode === 200 ? 0 : 1) })"

ENTRYPOINT ["node", "server.js"]
```

### Nginx Static Site

```dockerfile
# ── AC-DF-MULTISTAGE ──
FROM node:22-slim@sha256:2222222222222222222222222222222222222222222222222222222222222222 AS builder

# ── AC-DF-REPRODUCIBLE ──
ARG SOURCE_DATE_EPOCH=0

WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --ignore-scripts
COPY . .
RUN npm run build

# ── Runtime stage ──
FROM nginx:1.27-alpine@sha256:3333333333333333333333333333333333333333333333333333333333333333 AS runtime

# ── AC-DF-OCI-LABELS ──
LABEL org.opencontainers.image.source="" \
      org.opencontainers.image.revision="" \
      org.opencontainers.image.licenses=""

# ── AC-DF-SUID-SGID ──
RUN find / -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} + 2>/dev/null || true

# ── AC-DF-USER: nginx unprivileged mode ──
RUN sed -i 's/listen\s*80;/listen 8080;/' /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

# ── AC-DF-HEALTHCHECK ──
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --spider -q http://localhost:8080/ || exit 1

USER nginx
ENTRYPOINT ["nginx", "-g", "daemon off;"]
```

### Rust

```dockerfile
# ── AC-DF-MULTISTAGE ──
ARG RUST_VERSION=1.83
FROM rust:${RUST_VERSION}-slim@sha256:4444444444444444444444444444444444444444444444444444444444444444 AS builder

# ── AC-DF-REPRODUCIBLE ──
ARG SOURCE_DATE_EPOCH=0

WORKDIR /app

# ── Layer ordering: manifests before source ──
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main(){}" > src/main.rs
# ── AC-DF-CACHE-MOUNTS: BuildKit cache for cargo registry + target ──
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/app/target \
    cargo build --release && rm -rf src

COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/app/target \
    cargo build --release && \
    cp target/release/myapp /usr/local/bin/myapp

# ── Runtime stage: distroless for minimal attack surface ──
FROM gcr.io/distroless/cc-debian12@sha256:5555555555555555555555555555555555555555555555555555555555555555 AS runtime

# ── AC-DF-OCI-LABELS ──
LABEL org.opencontainers.image.source="" \
      org.opencontainers.image.revision="" \
      org.opencontainers.image.licenses=""

COPY --from=builder /usr/local/bin/myapp /usr/local/bin/myapp

# ── AC-DF-USER: distroless nonroot user ──
USER nonroot

EXPOSE 8080

# ── AC-DF-HEALTHCHECK: executable-form check for distroless ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/usr/local/bin/myapp", "--healthcheck"]

ENTRYPOINT ["/usr/local/bin/myapp"]
```

### Generic / Multi-purpose

```dockerfile
# ── AC-DF-MULTISTAGE ──
FROM debian:12-slim@sha256:6666666666666666666666666666666666666666666666666666666666666666 AS builder

# ── AC-DF-REPRODUCIBLE ──
ARG SOURCE_DATE_EPOCH=0

WORKDIR /app
COPY . .
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential && \
    make build && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/*

# ── Runtime stage ──
FROM debian:12-slim@sha256:6666666666666666666666666666666666666666666666666666666666666666 AS runtime

# ── AC-DF-OCI-LABELS ──
LABEL org.opencontainers.image.source="" \
      org.opencontainers.image.revision="" \
      org.opencontainers.image.licenses=""

# ── AC-DF-SUID-SGID ──
RUN find / -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} + 2>/dev/null || true

# ── AC-DF-USER ──
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app
COPY --from=builder /app/build/output .

RUN chown -R app:app /app
USER app

EXPOSE 8080

# ── AC-DF-HEALTHCHECK ──
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["/bin/sh", "-c", "test -x ./myapp"]

ENTRYPOINT ["./myapp"]
```

---

## Compose Template (Hardened)

Anchor structure mirrors the Rust tooling output (`x-hardening-core`,
`x-resource-defaults-compose`, `x-composite-restart`, `x-init-permissions-core`).

```yaml
# ── Hardened Compose Template ──
# Encodes invariants from policy-compose-balanced.yaml / policy-compose-enforcing.yaml
# Anchor structure matches the Rust tooling output for consistency.

# ── AC-CMP-READONLY + AC-CMP-CAPDROP + AC-CMP-NNP ──
x-hardening-core: &hardening_core
  cap_drop:
    - ALL
  read_only: true
  security_opt:
    - no-new-privileges:true

# ── AC-CMP-RESOURCES: compose-mode resource limits ──
x-resource-defaults-compose: &resource_defaults_compose
  cpus: "1.0"
  mem_limit: 512m
  pids_limit: 256

# ── AC-CMP-RESTART + AC-CMP-WRITABLE: shared restart/tmpfs defaults ──
x-composite-restart: &composite_restart
  restart: unless-stopped
  tmpfs:
    - /tmp:rw,noexec,nosuid,nodev,size=64m
    - /run:rw,noexec,nosuid,nodev,size=16m
    - /var/run:rw,noexec,nosuid,nodev,size=16m

# ── AC-CMP-PERMS-INIT: shared init-permissions anchor ──
x-init-permissions-core: &init_permissions_core
  cap_add:
    - CHOWN
    - FOWNER
  cap_drop:
    - ALL
  network_mode: none
  read_only: true
  restart: "no"
  security_opt:
    - no-new-privileges:true
  user: "0:0"

# ── AC-CMP-HEALTH: shared healthcheck defaults ──
x-healthcheck-defaults: &healthcheck_defaults
  interval: 30s
  timeout: 5s
  start_period: 10s
  retries: 3

services:
  app:
    <<: [*hardening_core, *resource_defaults_compose, *composite_restart]
    image: myapp:latest  # Replace with digest-pinned reference
    # ── AC-CMP-USER: non-root runtime ──
    user: "1000:1000"
    volumes:
      - app-data:/app/data
    # ── AC-CMP-SECRETS: sensitive values via secrets, not env ──
    secrets:
      - db_password
    environment:
      DB_HOST: db
      DB_NAME: myapp
    healthcheck:
      <<: *healthcheck_defaults
      test: ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
    depends_on:
      db:
        condition: service_healthy
      app-init-perms:
        condition: service_completed_successfully
    networks:
      - internal

  db:
    <<: [*hardening_core, *resource_defaults_compose, *composite_restart]
    image: postgres:16-alpine  # Replace with digest-pinned reference
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
    depends_on:
      db-init-perms:
        condition: service_completed_successfully
    networks:
      - internal

  # ── AC-CMP-PERMS-INIT: permission init sidecars ──
  app-init-perms:
    <<: [*hardening_core, *init_permissions_core, *resource_defaults_compose]
    image: docker.io/library/alpine@sha256:<replace-with-verified-digest>
    tmpfs:
      - /tmp:rw,noexec,nosuid,nodev,size=16m
      - /run:rw,noexec,nosuid,nodev,size=16m
      - /var/run:rw,noexec,nosuid,nodev,size=16m
    command:
      - /bin/sh
      - -euxc
      - |
        set -eu
        for path in /mnt/perm-0; do
          mkdir -p "$$path"
          owner="$$(stat -c '%u:%g' "$$path" 2>/dev/null || true)"
          if [ "$$owner" != "1000:1000" ]; then chown -R 1000:1000 "$$path"; fi
        done
    volumes:
      - app-data:/mnt/perm-0

  db-init-perms:
    <<: [*hardening_core, *init_permissions_core, *resource_defaults_compose]
    image: docker.io/library/alpine@sha256:<replace-with-verified-digest>
    tmpfs:
      - /tmp:rw,noexec,nosuid,nodev,size=16m
      - /run:rw,noexec,nosuid,nodev,size=16m
      - /var/run:rw,noexec,nosuid,nodev,size=16m
    command:
      - /bin/sh
      - -euxc
      - |
        set -eu
        for path in /mnt/perm-0; do
          mkdir -p "$$path"
          owner="$$(stat -c '%u:%g' "$$path" 2>/dev/null || true)"
          if [ "$$owner" != "999:999" ]; then chown -R 999:999 "$$path"; fi
        done
    volumes:
      - db-data:/mnt/perm-0

volumes:
  app-data:
  db-data:

secrets:
  db_password:
    file: ./secrets/db_password.txt

networks:
  internal:
    driver: bridge
```

### Usage Notes

- **Anchor pattern**: Four composable anchors (`hardening_core`, `resource_defaults_compose`,
  `composite_restart`, `init_permissions_core`) merged via `<<: [*a, *b, *c]`. This matches
  the Rust tooling output shape. Generated anchor names may include a content-derived suffix.
  Override per-service as needed (e.g., add `cap_add: [NET_BIND_SERVICE]` for port 80).
- **Merge keys (`<<`)**: Compose policy evaluation materializes YAML merge keys before applying
  rules, so inherited values from anchors are evaluated the same as explicit keys.
- **Resource limits**: Use `cpus`, `mem_limit`, `pids_limit` (Compose v2 flat keys), not
  `deploy.resources.limits` (which requires Swarm mode or `--compatibility`).
- **Init sidecars**: The `app-init-perms` and `db-init-perms` services run on every
  `docker compose up`, check current ownership with `stat`, conditionally `chown` if
  needed, and exit immediately. No manual profile activation is required. The conditional
  check avoids unnecessary filesystem writes on subsequent starts. These sidecars are
  referenced via `depends_on: { *-init-perms: { condition: service_completed_successfully } }`
  to guarantee volume ownership is correct before the main service starts.
- **Secrets**: Replace `file:` source with `external: true` for production (pre-created secrets).
- **Digest pinning**: Replace `image: myapp:latest` with `image: myapp@sha256:...` before
  production deployment.
- **tmpfs**: All services mount `/tmp`, `/run`, and `/var/run` with `noexec,nosuid,nodev`
  options. This is required because `read_only: true` makes the root filesystem immutable.
