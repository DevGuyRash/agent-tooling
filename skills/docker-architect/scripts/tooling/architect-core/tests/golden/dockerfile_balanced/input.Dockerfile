ARG SOURCE_DATE_EPOCH
FROM docker.io/library/debian:12-slim@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa AS builder
RUN --mount=type=cache,target=/var/cache/apt apt-get update && apt-get install -y curl

FROM docker.io/library/debian:12-slim@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb AS runtime
LABEL org.opencontainers.image.source=unknown
LABEL org.opencontainers.image.revision=unknown
LABEL org.opencontainers.image.licenses=unknown
COPY --from=builder /usr/bin/curl /usr/bin/curl
USER 65532:65532
HEALTHCHECK CMD ["curl", "-f", "http://localhost:8080/health"]
CMD ["curl", "--version"]
