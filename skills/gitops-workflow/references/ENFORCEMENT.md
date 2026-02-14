# Enforcement & Automation (Deterministic by Default)

This skill supports advisory templates, but governance controls should be applied as deterministic desired state using:

- `scripts/repo-governance.py`
- `scripts/governance-enforce.sh`
- `assets/config/github-governance-policy.v1.json`

Reference docs:
- [GOVERNANCE_POLICY.md](GOVERNANCE_POLICY.md)
- [GH_GOVERNANCE_RUNBOOK.md](GH_GOVERNANCE_RUNBOOK.md)

## 1) Required flow: validate -> plan -> apply -> audit

Run in this order for every governance change:

```bash
python3 scripts/repo-governance.py validate --policy assets/config/github-governance-policy.v1.json
python3 scripts/repo-governance.py plan --policy assets/config/github-governance-policy.v1.json --repo <owner/repo>
python3 scripts/repo-governance.py apply --policy assets/config/github-governance-policy.v1.json --repo <owner/repo> --write-codeowners
python3 scripts/repo-governance.py audit --policy assets/config/github-governance-policy.v1.json --repo <owner/repo> --format json
```

Single-command wrapper:

```bash
bash scripts/governance-enforce.sh --policy assets/config/github-governance-policy.v1.json --repo <owner/repo>
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
bash scripts/required-checks-discover.sh --repo <owner/repo>
```

## 4) Label baseline export

To export current labels into policy format:

```bash
bash scripts/labels-export.sh --repo <owner/repo>
```

## 5) CI templates remain useful

These workflow templates still provide enforcement signal consumed by branch/ruleset protections:
- `assets/github/workflows/pr-title-lint.yml`
- `assets/github/workflows/commitlint.yml`
- `assets/github/workflows/release-please.yml` (optional release automation)

Tip: if using merge queue, ensure required workflows also run on `merge_group`.
