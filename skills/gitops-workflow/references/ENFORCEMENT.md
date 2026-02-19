# Enforcement & Automation (Deterministic by Default)

This skill supports advisory templates, but governance controls should be applied as deterministic desired state using:

- `scripts/repo-governance.py`
- `scripts/governance-enforce.sh`
- `assets/config/github-governance-policy.v1.json`

Command context:

```bash
SKILL_ROOT=<absolute-path-to-gitops-workflow>
```

Reference docs:
- [GOVERNANCE_POLICY.md](GOVERNANCE_POLICY.md)
- [GH_GOVERNANCE_RUNBOOK.md](GH_GOVERNANCE_RUNBOOK.md)

## 1) Required flow: validate -> plan -> apply -> audit

Run in this order for every governance change:

```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" validate --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json"
python3 "$SKILL_ROOT/scripts/repo-governance.py" plan --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo>
python3 "$SKILL_ROOT/scripts/repo-governance.py" apply --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo> --write-codeowners
python3 "$SKILL_ROOT/scripts/repo-governance.py" audit --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo> --format json
```

Single-command wrapper:

```bash
bash "$SKILL_ROOT/scripts/governance-enforce.sh" --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json" --repo <owner/repo>
```

Behavior:
- `plan`/`audit` exit `3` when drift exists.
- `apply` is fail-closed and exits non-zero on partial failure.
- `apply` requires `--write-codeowners` when CODEOWNERS drift exists.

## 2) Deterministic controls covered

Policy reconciliation manages:
- rulesets (or legacy branch protection fallback when enabled)
- required checks
- CODEOWNERS content (local file)
- exact label set membership (create/update/delete)

## 3) Required checks discovery

To seed policy with real check context names:

```bash
bash "$SKILL_ROOT/scripts/required-checks-discover.sh" --repo <owner/repo>
```

## 4) Label baseline export

To export current labels into policy format:

```bash
bash "$SKILL_ROOT/scripts/labels-export.sh" --repo <owner/repo>
```

## 5) CI templates remain useful

These workflow templates still provide enforcement signal consumed by branch/ruleset protections:
- `assets/github/workflows/pr-title-lint.yml`
- `assets/github/workflows/commitlint.yml`
- `assets/github/workflows/sensitive-scan.yml`
- `assets/github/workflows/release-please.yml` (optional release automation)

Tip: if using merge queue, ensure required workflows also run on `merge_group`.

## 6) Local sensitive-data gate (recommended fail-closed)

Install managed pre-commit hook once per repo:

```bash
bash "$SKILL_ROOT/scripts/install-hooks.sh" --repo <path-to-repo>
```

Manual deterministic scan commands:

```bash
bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --staged --redact --repo <path-to-repo>
bash "$SKILL_ROOT/scripts/sensitive-scan.sh" --all --redact --repo <path-to-repo>
```

Notes:
- The scanner uses `assets/config/gitleaks.toml` by default.
- For GitHub Actions template usage, copy that file into `.github/gitleaks.toml`.
- It tries to update to the latest `gitleaks` when network is available.
- Set `SENSITIVE_SCAN_GITLEAKS_VERSION=vX.Y.Z` to pin.
- Set `SENSITIVE_SCAN_DISABLE_UPDATE=1` for fully pinned/offline mode.
- PATH `gitleaks` fallback is disabled by default; set `SENSITIVE_SCAN_ALLOW_PATH_BIN=1` only if explicitly required.
