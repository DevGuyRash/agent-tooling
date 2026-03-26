# JavaScript and TypeScript Commands

Use this file when the repo uses `package.json`.

## Detection order

1. package manager declared in `packageManager`
2. lockfile:
   - `pnpm-lock.yaml`
   - `yarn.lock`
   - `package-lock.json`
   - `bun.lockb`, `bun.lock`
3. fallback to npm

## First rule

Prefer existing scripts from `package.json`.

Examples:
- `build`
- `test`
- `lint`
- `format`
- `fmt`
- `fmt:check`
- `ci`
- `dev`

A wrapper justfile should delegate to those scripts before inventing direct
ESLint, Prettier, or Vite commands.

## Package-manager command families

### npm

```text
bootstrap  npm ci
build      npm run build --if-present
test       npm run test --if-present
lint       npm run lint --if-present
fmt        npm run format --if-present
```

### pnpm

```text
bootstrap  pnpm install --frozen-lockfile
build      pnpm run build --if-present
test       pnpm run test --if-present
lint       pnpm run lint --if-present
fmt        pnpm run format --if-present
```

### yarn

Use the repo’s existing lockfile and conventions. The safest generic bootstrap
is `yarn install`. Prefer a stricter install mode only when the repo already
uses it consistently.

### bun

```text
bootstrap  bun install
build      bun run build
test       bun run test
lint       bun run lint
fmt        bun run format
```

## Framework signals

- Next.js
- Nuxt
- Remix
- SvelteKit
- Vite
- Astro
- NestJS

These matter because they often determine whether `build`, `test`, and `dev`
scripts already exist.

## Workspace guidance

For npm or pnpm workspaces, prefer workspace-native commands when the repo
already uses them. Otherwise use per-package prefixed recipes plus aggregate
top-level recipes.

## Formatting fallback

If the repo has no `format` script but clearly depends on Prettier, a fallback
command is reasonable:

```text
prettier --write .
prettier --check .
```

Use that only when the repo does not already express a preferred formatting
entry point.
