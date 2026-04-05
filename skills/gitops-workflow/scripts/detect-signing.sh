#!/usr/bin/env bash
# detect-signing.sh - Detect whether commit signing is available in the current environment.
#
# Usage:
#   bash scripts/detect-signing.sh
#
# Exit codes:
#   0  Signing available and working.
#   1  Signing configured but unavailable (remote SSH, agent timeout, etc.).
#   2  Signing not configured.
#
# Output: JSON object to stdout with signing state details.

set -euo pipefail

# --- help -------------------------------------------------------------------

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,/^$/{ s/^# \?//; p }' "$0"
  exit 0
fi

# --- helpers -----------------------------------------------------------------

json_out() {
  local configured="$1" available="$2" remote="$3" fmt="$4" rec="$5"
  printf '{"signing_configured": %s, "signing_available": %s, "remote_session": %s, "gpg_format": "%s", "recommendation": "%s"}\n' \
    "$configured" "$available" "$remote" "$fmt" "$rec"
}

# --- check: signing configured? ---------------------------------------------

gpgsign="$(git config --get commit.gpgsign 2>/dev/null || true)"

if [[ -z "$gpgsign" || "$gpgsign" == "false" ]]; then
  json_out false false false "" "not-configured"
  exit 2
fi

# --- detect remote SSH session -----------------------------------------------

remote_session=false
if [[ -n "${SSH_CONNECTION:-}" || -n "${SSH_CLIENT:-}" ]]; then
  remote_session=true
fi

# --- determine signing format ------------------------------------------------

gpg_format="$(git config --get gpg.format 2>/dev/null || true)"
# Normalise: empty or "openpgp" both mean classic GPG.
if [[ -z "$gpg_format" || "$gpg_format" == "openpgp" ]]; then
  gpg_format="gpg"
fi

# --- lightweight signing probe -----------------------------------------------

TMPDIR_PROBE=""
cleanup() { [[ -n "$TMPDIR_PROBE" ]] && rm -rf "$TMPDIR_PROBE"; }
trap cleanup EXIT

TMPDIR_PROBE="$(mktemp -d)"

probe_ok=false

# Build the probe inside a subshell so failures don't kill the script.
if (
  cd "$TMPDIR_PROBE"
  git init --quiet
  git config user.email "probe@localhost"
  git config user.name "probe"
  git config commit.gpgsign true
  # Carry over the caller's signing configuration.
  if [[ "$gpg_format" == "ssh" ]]; then
    git config gpg.format ssh
    ssh_key="$(git config --global --get user.signingkey 2>/dev/null || true)"
    [[ -n "$ssh_key" ]] && git config user.signingkey "$ssh_key"
    allowed="$(git config --global --get gpg.ssh.allowedSignersFile 2>/dev/null || true)"
    [[ -n "$allowed" ]] && git config gpg.ssh.allowedSignersFile "$allowed"
  else
    gpg_program="$(git config --global --get gpg.program 2>/dev/null || true)"
    [[ -n "$gpg_program" ]] && git config gpg.program "$gpg_program"
    signing_key="$(git config --global --get user.signingkey 2>/dev/null || true)"
    [[ -n "$signing_key" ]] && git config user.signingkey "$signing_key"
  fi
  # Attempt a signed commit with a 2-second timeout.
  touch probe-file
  git add probe-file
  if command -v timeout >/dev/null 2>&1; then
    timeout 2 git commit --quiet --allow-empty-message -m "" 2>/dev/null
  else
    # Fallback: use perl alarm if timeout is missing.
    perl -e 'alarm 2; exec @ARGV' -- git commit --quiet --allow-empty-message -m "" 2>/dev/null
  fi
) 2>/dev/null; then
  probe_ok=true
fi

# --- output ------------------------------------------------------------------

if [[ "$probe_ok" == "true" ]]; then
  json_out true true "$remote_session" "$gpg_format" "available"
  exit 0
else
  json_out true false "$remote_session" "$gpg_format" "skip"
  exit 1
fi
