<type>[(<scope>)]: <short imperative summary>

## Overview

<!-- AGENT: Write 1-2 sentences summarizing what this PR achieves and why. -->

## New Features

<!-- AGENT: Describe new features in natural prose bullets. Remove this section if not applicable. -->

## What's Changed

<!-- AGENT: Describe non-feature changes in natural prose bullets. Remove this section if not applicable. -->

## Bug Fixes

<!-- AGENT: Describe bug fixes in natural prose bullets. Remove this section if not applicable. -->

## Breaking Changes

<!-- AGENT: Describe breaking changes and migration steps. Remove this section if not applicable. -->

## Commits

- `<SHA>` <first-line commit subject>
- `<SHA>` <first-line commit subject>

## Refs

- Fixes #123
- owner/repo#456
- https://github.com/owner/repo/issues/789

Two-phase workflow:
1. Generate skeleton: `pr-merge-squash.sh <number> --body-out /tmp/squash.md --dry-run`
2. Fill the `<!-- AGENT: -->` placeholders with natural prose, then merge: `pr-merge-squash.sh <number> --body-file /tmp/squash.md`

For fully mechanical bodies (legacy): add `--deterministic` to skip placeholders.
