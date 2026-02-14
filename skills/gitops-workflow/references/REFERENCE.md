# Reference Guide

This skill follows the Open Agent Skills format:

- A skill is a directory containing a required `SKILL.md`.
- Optional supporting folders include `scripts/`, `references/`, and `assets/`.
- Skills are designed for progressive disclosure: metadata → instructions → resources.

This skill’s structure:

- `SKILL.md` – orchestration + the main workflow playbooks (keep this short).
- `references/` – deeper checklists, conventions, and enforcement guidance.
- `scripts/` – optional automation helpers (git + GitHub CLI + Python).
- `assets/` – copy/paste templates (PR body, squash message, release notes, CI workflows).

Governance-specific references:
- [ENFORCEMENT.md](ENFORCEMENT.md)
- [GOVERNANCE_POLICY.md](GOVERNANCE_POLICY.md)
- [GH_GOVERNANCE_RUNBOOK.md](GH_GOVERNANCE_RUNBOOK.md)
- [SCRIPT_ROUTING.md](SCRIPT_ROUTING.md)

## How to install

Copy this directory into a skills-discovery location supported by your agent product, for example:

- Project-local: `.skills/gitops-workflow/`
- Claude Code: `.claude/skills/gitops-workflow/`
- Cursor: `.cursor/skills/gitops-workflow/`
- Generic agents: `.agent/skills/gitops-workflow/`

(Exact folder conventions vary by agent implementation.)

## How to validate

Use the `skills-ref` reference tool to validate the frontmatter and structure:

```bash
skills-ref validate ./gitops-workflow
```

## How to adopt incrementally

You can adopt this skill in layers:

1. **Instructions only**: agent follows the playbooks + checklists.
2. **Templates**: copy PR template + squash/release templates into `.github/`.
3. **CI enforcement**: add GitHub Actions from `assets/github/workflows/`.
4. **Local hooks** (optional): add commit-msg hooks to catch issues earlier.
5. **Release automation** (optional): integrate `release-please` or your release process.

See [ENFORCEMENT.md](ENFORCEMENT.md) for details.
