# .dockerignore Templates

Use these templates alongside every Dockerfile. A `.dockerignore` prevents build-context
bloat, avoids leaking secrets into layers, and speeds up `COPY . .` operations.

> **Policy**: AC-DF-DOCKERIGNORE — every Dockerfile must have a companion `.dockerignore`.

---

## Generic (all projects)

```dockerignore
# Version control
.git
.gitignore

# CI/CD artifacts
.github
.gitlab-ci.yml
.circleci

# IDE / editor
.vscode
.idea
*.swp
*.swo
*~

# Docker files (prevent recursive context)
Dockerfile*
compose*.yml
compose*.yaml
.dockerignore

# Documentation
README*
LICENSE
CHANGELOG*
docs/

# Secrets — never send to build context
.env
.env.*
*.pem
*.key
*.crt
secrets/
```

**Rationale**: `.git` alone can add hundreds of MB. IDE and CI files are never needed at
runtime. Excluding `Dockerfile*` and compose files prevents accidental recursive copies.
Secrets exclusions are a defense-in-depth layer on top of multi-stage builds.

---

## Python

Extends the generic template with Python-specific entries.

```dockerignore
# --- Generic (copy from above) ---
.git
.gitignore
.github
.vscode
.idea
Dockerfile*
compose*.yml
compose*.yaml
.dockerignore
README*
LICENSE
docs/
.env
.env.*
*.pem
*.key

# --- Python-specific ---
__pycache__
*.pyc
*.pyo
*.egg-info
dist/
build/
.eggs/
.mypy_cache/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
.tox/
.nox/
venv/
.venv/
env/
```

**Rationale**: `__pycache__` and `.pyc` files are platform-specific bytecode — copying
them into a container breaks portability. Virtual environments (`venv/`, `.venv/`) contain
host-platform binaries and should never enter the build context.

---

## Node.js

```dockerignore
# --- Generic (copy from above) ---
.git
.gitignore
.github
.vscode
.idea
Dockerfile*
compose*.yml
compose*.yaml
.dockerignore
README*
LICENSE
docs/
.env
.env.*
*.pem
*.key

# --- Node-specific ---
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-store/
.next/
.nuxt/
dist/
coverage/
.turbo/
.eslintcache
```

**Rationale**: `node_modules/` is the single largest context-bloat offender — it can
exceed 500 MB. It must be excluded because `npm ci` / `yarn install --frozen-lockfile`
inside the container produces a Linux-native dependency tree.

---

## Rust

```dockerignore
# --- Generic (copy from above) ---
.git
.gitignore
.github
.vscode
.idea
Dockerfile*
compose*.yml
compose*.yaml
.dockerignore
README*
LICENSE
docs/
.env
.env.*
*.pem
*.key

# --- Rust-specific ---
target/
*.rs.bk
```

**Rationale**: `target/` contains host-platform compilation artifacts and can easily
exceed 1 GB. Cargo rebuilds inside the container with the correct target triple.

---

## Go

```dockerignore
# --- Generic (copy from above) ---
.git
.gitignore
.github
.vscode
.idea
Dockerfile*
compose*.yml
compose*.yaml
.dockerignore
README*
LICENSE
docs/
.env
.env.*
*.pem
*.key

# --- Go-specific ---
vendor/
bin/
*.exe
*.test
*.out
coverage.txt
```

**Rationale**: Go binaries are statically compiled inside the builder stage. The `vendor/`
directory (if present) should be excluded when using `go mod download` in the builder;
keep it only if you vendor explicitly and skip the download step.
