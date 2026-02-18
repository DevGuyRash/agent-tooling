# GitHub Governance Runbook

This runbook is for deterministic, fail-closed enforcement operations.

## Required tooling

- `gh` authenticated for the target org/repo
- `python3`
- `jq` (for helper discovery/export scripts)

## Required token capabilities

`gh auth status` token should support repository administration APIs.
If scope is insufficient, commands fail with exit code `5`.

## Standard command sequence

Set `SKILL_ROOT` to the installed `gitops-workflow` skill directory:
```bash
export SKILL_ROOT="/absolute/path/to/gitops-workflow"
```

1. Validate policy:
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" validate --policy "$SKILL_ROOT/assets/config/github-governance-policy.v1.json"
```

2. Plan drift (non-mutating):
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" plan --policy <policy> --repo <owner/repo>
```

3. Apply (mutating):
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" apply --policy <policy> --repo <owner/repo> --write-codeowners
```

4. Audit post-apply:
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" audit --policy <policy> --repo <owner/repo> --format json
```

Wrapper equivalent:
```bash
bash "$SKILL_ROOT/scripts/governance-enforce.sh" --policy <policy> --repo <owner/repo>
```

## Exit codes

- `0`: success / no drift
- `2`: invalid policy or unsupported capability
- `3`: drift detected (plan/audit)
- `4`: apply failed or partially applied
- `5`: permission/token insufficiency

## Failure modes

- Rulesets API unavailable:
  - if `options.allowLegacyBranchProtection=false`, fail with code `2`
  - if true, fallback to branch protection endpoint
- CODEOWNERS drift during `apply` without `--write-codeowners`:
  - fail with code `4`
- Partial apply errors:
  - fail with code `4`; output includes failing resources

## Safe rollback

- Keep policy file under version control.
- Revert policy commit if incorrect.
- Re-run `apply` with reverted policy to reconcile state back.

## Bootstrap helpers

- Discover checks:
```bash
bash "$SKILL_ROOT/scripts/required-checks-discover.sh" --repo <owner/repo>
```

- Export labels:
```bash
bash "$SKILL_ROOT/scripts/labels-export.sh" --repo <owner/repo>
```

- Export baseline policy:
```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" export --repo <owner/repo> --out /tmp/policy.json
```
