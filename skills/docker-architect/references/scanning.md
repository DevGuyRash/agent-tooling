# Container Scanning Reference

Post-generation scanning validates that emitted Dockerfiles and Compose files meet
hardening invariants. Run these tools after every generation pass.

---

## 1. hadolint — Dockerfile Linter

### Install

```bash
# Binary (Linux x86_64, latest stable)
HADOLINT_VERSION="<latest stable>"
curl -sL "https://github.com/hadolint/hadolint/releases/download/${HADOLINT_VERSION}/hadolint-Linux-x86_64" \
  -o /usr/local/bin/hadolint
chmod +x /usr/local/bin/hadolint
curl -sL "https://github.com/hadolint/hadolint/releases/download/${HADOLINT_VERSION}/hadolint-Linux-x86_64.sha256" \
  -o /tmp/hadolint.sha256
echo "$(cat /tmp/hadolint.sha256)  /usr/local/bin/hadolint" | sha256sum -c -

# Container (no install)
docker run --rm -i hadolint/hadolint < Dockerfile
```

### Usage

```bash
# Lint a single Dockerfile
hadolint Dockerfile

# Strict mode — treat warnings as errors
hadolint --failure-threshold warning Dockerfile

# Ignore specific rules
hadolint --ignore DL3008 --ignore DL3013 Dockerfile

# Output as JSON (for CI parsing)
hadolint -f json Dockerfile
```

### Key rules to watch

| Rule   | Meaning                                    |
|--------|--------------------------------------------|
| DL3006 | Always tag the version in FROM             |
| DL3007 | Using `latest` is not deterministic        |
| DL3008 | Pin versions in `apt-get install`          |
| DL3025 | Use JSON form for CMD/ENTRYPOINT           |
| DL4006 | Set `SHELL` option `-o pipefail`           |

---

## 2. Trivy — Vulnerability Scanner

### Install

```bash
# Binary (Linux)
TRIVY_VERSION="<latest stable>"
curl -fsSLO "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"
curl -fsSLO "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz.pem"
curl -fsSLO "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz.sig"
curl -fsSLO "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_checksums.txt"
grep "trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" "trivy_${TRIVY_VERSION}_checksums.txt" | sha256sum -c -
tar -xzf "trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" trivy
install -m 0755 trivy /usr/local/bin/trivy

# Container
docker run --rm aquasec/trivy image <image-name>
```

### Usage

```bash
# Scan a built image
trivy image myapp:latest

# Scan a Dockerfile (config scanning)
trivy config Dockerfile

# Scan a Compose file
trivy config compose.yaml

# Scan with severity filter
trivy image --severity HIGH,CRITICAL myapp:latest

# Output as JSON
trivy image -f json -o results.json myapp:latest

# Fail CI on HIGH/CRITICAL
trivy image --exit-code 1 --severity HIGH,CRITICAL myapp:latest
```

For compose misconfiguration coverage, use Trivy `v0.51.0+` and align findings
with the skill policy rule sets:
- Compose restart hardening: `AC-CMP-RESTART` (`policy-compose-balanced.yaml`)
- Swarm restart hardening: `AC-SWM-RESTART` (`policy-swarm-balanced.yaml`)

---

## 3. Docker Scout — Supply Chain Analysis

### Install

Docker Scout is included with Docker Desktop 4.17+. For standalone:

```bash
# CLI plugin (Linux amd64)
SCOUT_VERSION="<latest stable>"
curl -fsSLO "https://github.com/docker/scout-cli/releases/download/v${SCOUT_VERSION}/docker-scout_${SCOUT_VERSION}_linux_amd64.tar.gz"
curl -fsSLO "https://github.com/docker/scout-cli/releases/download/v${SCOUT_VERSION}/checksums.txt"
grep "docker-scout_${SCOUT_VERSION}_linux_amd64.tar.gz" checksums.txt | sha256sum -c -
tar -xzf "docker-scout_${SCOUT_VERSION}_linux_amd64.tar.gz" docker-scout
install -Dm0755 docker-scout "${HOME}/.docker/cli-plugins/docker-scout"

# Verify
docker scout version
```

### Usage

```bash
# Quick vulnerability overview
docker scout quickview myapp:latest

# Full CVE list
docker scout cves myapp:latest

# Compare two image versions
docker scout compare myapp:latest --to myapp:previous

# Recommendations for base image updates
docker scout recommendations myapp:latest
```

---

## 4. Compose Validation

Always validate compose files before deployment:

```bash
# Syntax + schema validation (prints resolved config or errors)
docker compose -f compose.yaml config

# Quiet mode — exit code only (for CI)
docker compose -f compose.yaml config -q

# Validate with specific profiles
docker compose -f compose.yaml --profile production config

# Validate multiple compose files (override chain)
docker compose -f compose.yaml -f compose.override.yaml config
```

---

## 5. Recommended CI Pipeline Order

Run scanning stages in this order for fastest feedback:

```
1. hadolint Dockerfile                          # ~1s  — syntax + best practices
2. docker compose config -q                     # ~1s  — compose schema validation
3. trivy config Dockerfile                      # ~3s  — Dockerfile misconfig scan
4. trivy config compose.yaml                    # ~3s  — compose misconfig scan
5. docker build -t myapp:ci .                   # build the image
6. trivy image --exit-code 1 \
     --severity HIGH,CRITICAL myapp:ci          # ~30s — image vulnerability scan
7. docker scout quickview myapp:ci              # supply chain overview (optional)
```

**Rationale**: Static analysis (steps 1-4) runs before the build to catch issues early.
Image scanning (steps 6-7) runs after the build since it requires a built image. This
ordering minimizes wasted build time on files that would fail linting.
