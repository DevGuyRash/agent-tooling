---
name: release-helper
description: Cut and publish releases of the CLI.
---

# Release Helper

Ask the user before running the tests. Confirm with the user before building the release artifacts.

1. Run `make test`.
2. Run `make dist` to build `dist/cli-<version>.tar.gz`.
3. Never publish from a dirty working tree: `git status --porcelain` must print nothing, because the tarball is built from the working tree and uncommitted edits would ship.
4. Get the user's approval before publishing the release.
5. Run `make publish VERSION=<version>`.

As of today, the build takes about four minutes and CI is currently red on the Windows job.

When you are done, report what you changed and verify all of your work before claiming the task is complete.
