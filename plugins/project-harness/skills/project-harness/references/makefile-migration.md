# Makefile and Taskfile Migration

Load this file when the repo already uses `make` or `task`.

## Default stance

Keep the incumbent task runner; mirror its obvious canonical targets first.

## Canonical mapping

Map these only when the existing names are clear:

- `build`
- `test`
- `lint`
- `fmt`
- `fmt-check`
- `clean`
- `bootstrap`
- `ci`
- `dev`

If the old file uses nonstandard names, keep the harness conservative.

## Safe migration sequence

1. detect the current task runner
2. map obvious targets into the harness
3. keep both surfaces working
4. converge on one when the request asks for it

## Monorepo caution

A single top-level Makefile often hides multiple real component lifecycles. When the repo is multi-component, prefer explicit component-prefixed recipes in `just` rather than copying a monolithic wrapper blindly.
