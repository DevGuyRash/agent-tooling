# Existing Files and Safe Update Rules

Load this file before writing into a real repo.

The generator is conservative on purpose.

## Managed versus unmanaged targets

Generated files contain the managed marker:

```text
# project-harness: managed-file
```

Files with that marker may be overwritten by later `update` runs.
Files without that marker are treated as unmanaged and are **not** force-merged.

## Targets this skill may write directly

- `justfile`
- `.github/workflows/ci.yml`
- `.github/workflows/release-cross-os.yml`
- `githooks/pre-push`
- `.gitignore` additions
- `.gitattributes` additions for `dist/**` when Git LFS is selected
- `.local/harness/state.json`
- `.local/harness/render/*` candidate files

## Candidate-first behavior

When a target file already exists and is unmanaged:
- the real target is left alone
- a candidate file is written under `.local/harness/render/`
- state records the target under `candidate_only`

Typical candidate files:
- `.local/harness/render/justfile`
- `.local/harness/render/ci.yml`
- `.local/harness/render/release-cross-os.yml`
- `.local/harness/render/githooks/pre-push`
- `.local/harness/render/.gitattributes`

## Files that are read but not rewritten

The generator may inspect these but does not rewrite them automatically:
- `Makefile`
- `Taskfile.yml`
- `package.json`
- `Cargo.toml`
- `pyproject.toml`
- `pom.xml`
- `go.mod`
- Dockerfiles and compose files

## `.gitignore` behavior

`update` may append:
- `.local/` always
- `dist/` for `local-dist`

It does **not** remove existing ignore rules automatically.
If `dist/` is ignored but you selected a committed-dist architecture, the skill
warns instead of silently changing that policy.

## `.gitattributes` behavior

If you explicitly select `git-lfs` with `committed-dist` or `cross-os-dist`,
`update` may append:

```text
# project-harness: track committed dist outputs with Git LFS
dist/** filter=lfs diff=lfs merge=lfs -text
```

This is additive and intentionally small.
It does not rewrite broader `.gitattributes` policy.

## Existing Makefile or Taskfile repos

Do not delete the incumbent task runner first.
Generate the harness beside it, map obvious canonical targets, and only then
choose whether the repo wants to keep both surfaces or converge on one.
