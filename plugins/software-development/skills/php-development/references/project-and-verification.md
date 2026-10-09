# Project Contract and Verification

Read this reference for PHP versions, SAPIs, Composer, extensions, dependencies, project metadata, tests, or verification work.

## Discover the runtime and project shape

Inspect applicable configuration:

- `composer.json`, `composer.lock`, `require`, `require-dev`, `autoload`, `autoload-dev`, scripts, plugins, and repositories.
- The `php` and `ext-*` requirements, `config.platform`, platform packages, and extension-specific behavior.
- CI matrices, containers, production images, web-server/FPM configuration, CLI jobs, and relevant ini settings.
- Framework bootstrap, package entry points, generated code, caches, and files excluded from version control.
- PHPUnit, Pest, Codeception, Behat, PHPStan, Psalm, PHPCS, PHP-CS-Fixer, Rector, or repository-selected tools.

In a monorepo, find the Composer root and runtime boundary that own the changed code. A root lockfile or analyzer configuration may not govern every nested package.

## Reconcile supported PHP

Derive support from Composer constraints, CI, deployment, framework requirements, extensions, and documented consumers. The local CLI version does not prove production SAPI behavior. CLI and FPM/Apache can load different ini files and extensions.

`config.platform` influences dependency resolution; it does not emulate or verify the real runtime. Do not use syntax or APIs beyond the declared minimum. When declarations conflict, follow the lowest declared minimum rather than choosing the newest value.

## Manage Composer deliberately

- With a valid lock, prefer the repository's locked install path.
- Run update or require operations only to change dependency resolution, and scope changes when possible.
- Preserve runtime versus development requirements, extension constraints, repositories, stability, scripts, and plugin policy.
- Treat Composer plugins and scripts as code execution; constrain them for untrusted packages or environments.
- Follow repository policy for `composer.lock`. Applications and reusable libraries have different consumer effects, so always-commit and never-commit are both overbroad.
- Do not hand-edit generated lock or autoloader state.
- Treat optimized and authoritative autoloaders as deployment choices: authoritative classmaps can reject runtime-generated classes that ordinary PSR-4 fallback would find.

## Build verification evidence

Use project commands first. A proportionate sequence is:

1. Syntax or focused test for the changed behavior.
2. Configured static analysis and style check.
3. Relevant framework or integration suite.
4. `composer validate` for metadata/lock consistency; use the repository's warning policy when deciding whether `--strict` is required.
5. `composer check-platform-reqs` on the actual target for deployment-sensitive work; it checks real PHP/extensions rather than `config.platform`.
6. Supported PHP/SAPI/extension matrix where compatibility changed.

Verify through the project's existing test runner, analyzer, and formatter. Report exact command, scope, runtime/SAPI, result, and unavailable evidence.
