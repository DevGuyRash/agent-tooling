# Governance Policy Contract (`github-governance/v1`)

This policy file is the canonical desired state for deterministic repository governance.
Use it with:

```bash
export SKILL_ROOT="/absolute/path/to/gitops-workflow"
```

Then:

```bash
python3 "$SKILL_ROOT/scripts/repo-governance.py" validate --policy <file>
python3 "$SKILL_ROOT/scripts/repo-governance.py" plan --policy <file>
python3 "$SKILL_ROOT/scripts/repo-governance.py" apply --policy <file> --write-codeowners
python3 "$SKILL_ROOT/scripts/repo-governance.py" audit --policy <file> --format json
```

## Top-level keys

Required:
- `schemaVersion` (must be `github-governance/v1`)
- `repository` (`owner`, `name`, `defaultBranch`)

Optional (deterministic defaults applied by validator):
- `rulesets`
- `requiredChecks`
- `codeowners`
- `labels`
- `options`
- `bypass`

Unknown keys are rejected.

## `requiredChecks`

List of exact status check contexts to enforce in branch governance.

```json
"requiredChecks": ["commitlint", "validate PR title (Conventional Commits)"]
```

The reconciler sorts and de-duplicates this list.

## `labels`

Exact label inventory. Reconciliation is exact membership by default:
- create missing labels
- update mismatched color/description
- delete extra unmanaged labels

Each label must include:
- `name` (string)
- `color` (6-char hex, with or without leading `#`)
- `description` (string, optional)

## `codeowners`

```json
"codeowners": {
  "path": ".github/CODEOWNERS",
  "entries": [{"pattern": "*", "owners": ["@org/team"]}]
}
```

Owners must be one of:
- GitHub handle (`@user`)
- GitHub team (`@org/team`)
- email token (`name@example.com`)

## `options`

Supported options:
- `allowLegacyBranchProtection` (bool)
- `rulesetsExact` (bool)
- `managedRulesetName` (string)
- `requiredApprovingReviewCount` (int)
- `dismissStaleReviews` (bool)
- `requireCodeOwnerReview` (bool)
- `requireLastPushApproval` (bool)
- `requireLinearHistory` (bool)
- `requireSignedCommits` (bool)
- `blockForcePushes` (bool)

## `bypass`

Optional list of bypass actors copied into managed ruleset:

```json
{"actor_type":"Team","actor_id":12345,"bypass_mode":"pull_request"}
```

Allowed actor types:
- `OrganizationAdmin`
- `RepositoryRole`
- `Team`
- `Integration`

Allowed bypass modes:
- `always`
- `pull_request`
