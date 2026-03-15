# Fallback Templates — docker-bake.hcl (Image Mode)

Use this template when generating Image-mode architecture that includes Buildx Bake
support. The `docker-bake.hcl` file provides declarative build orchestration with
multi-platform support, reproducible builds, and supply-chain attestation controls.

---

## docker-bake.hcl Template

```hcl
# ── docker-bake.hcl ──
# Declarative build targets for Docker Buildx Bake.
# Supports reproducible builds, multi-platform images, SBOM, and provenance attestation.

# ── Variables ──

variable "SOURCE_DATE_EPOCH" {
  # Timestamp for reproducible builds (seconds since Unix epoch).
  # Set to a known value (e.g., git commit timestamp) for bit-for-bit reproducibility.
  # Example: SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
  default = "0"
}

variable "REGISTRY" {
  # Target container registry.
  default = "docker.io"
}

variable "IMAGE_NAME" {
  # Image name without registry prefix or tag.
  default = "myorg/myapp"
}

variable "VERSION" {
  # Image version tag. Override via CLI: VERSION=1.2.3 docker buildx bake release
  default = "latest"
}

# ── Groups ──

group "default" {
  targets = ["build"]
}

# ── Targets ──

# Local development build: single platform, no push.
target "build" {
  context    = "."
  dockerfile = "Dockerfile"
  tags       = ["${REGISTRY}/${IMAGE_NAME}:${VERSION}"]
  args = {
    SOURCE_DATE_EPOCH = "${SOURCE_DATE_EPOCH}"
  }
}

# Release build: multi-platform with SBOM and provenance attestation.
target "release" {
  inherits  = ["build"]
  platforms = ["linux/amd64", "linux/arm64"]
  tags = [
    "${REGISTRY}/${IMAGE_NAME}:${VERSION}",
    "${REGISTRY}/${IMAGE_NAME}:latest",
  ]
  attest = [
    "type=sbom",
    "type=provenance,mode=max",
  ]
}

# CI build: inherits from default, adds --no-cache for clean builds.
target "ci" {
  inherits = ["build"]
  no-cache = true
}
```

---

## Signing Guidance

After building and pushing the release image, sign it with `cosign`:

```bash
# ── Image Signing with Cosign ──
# Requires: cosign installed, COSIGN_KEY or keyless identity configured.

# Sign with a local key pair
cosign sign --key cosign.key ${REGISTRY}/${IMAGE_NAME}:${VERSION}

# Keyless signing via OIDC (e.g., GitHub Actions, GitLab CI)
cosign sign ${REGISTRY}/${IMAGE_NAME}:${VERSION}

# Verify signature
cosign verify --key cosign.pub ${REGISTRY}/${IMAGE_NAME}:${VERSION}

# Verify SBOM attestation
cosign verify-attestation --type spdxjson --key cosign.pub ${REGISTRY}/${IMAGE_NAME}:${VERSION}

# Verify provenance attestation
cosign verify-attestation --type slsaprovenance --key cosign.pub ${REGISTRY}/${IMAGE_NAME}:${VERSION}
```

---

## Usage Examples

```bash
# Local development build (single platform, no attestation)
docker buildx bake

# Release build with multi-platform + attestation (requires registry push)
docker buildx bake release --push

# CI build (clean, no cache)
docker buildx bake ci

# Override variables
VERSION=1.2.3 REGISTRY=ghcr.io IMAGE_NAME=myorg/myapp docker buildx bake release --push

# Reproducible build with fixed timestamp
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) docker buildx bake release --push
```

---

## Notes

- **`SOURCE_DATE_EPOCH`**: Setting this to a deterministic value (e.g., last git commit
  timestamp) makes builds reproducible. File timestamps, build IDs, and other
  non-deterministic metadata are normalized to this epoch.
- **Multi-platform**: The `release` target builds for `linux/amd64` and `linux/arm64`.
  Add platforms as needed (e.g., `linux/arm/v7` for IoT).
- **SBOM**: `attest: type=sbom` generates a Software Bill of Materials using BuildKit's
  built-in scanner. The SBOM is attached as an in-toto attestation.
- **Provenance**: `attest: type=provenance,mode=max` captures full build provenance
  including Dockerfile, build args, and source info. `mode=max` includes complete
  build steps (vs `mode=min` which captures only the final result).
- **`--push` required for attestation**: SBOM and provenance attestations are stored
  in the registry alongside the image manifest. They require `--push` or a local
  registry to persist.
