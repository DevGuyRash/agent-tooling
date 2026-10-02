---
name: python-development
description: >-
  Use for substantive Python source, stubs, or pyproject tooling. Covers typing, exceptions, resources, and concurrency; exclude Q&A, scratch code, and distribution/publication-only work.
---

# Python Development

This skill builds on the [Software Development Foundation](../../foundation.md).

Python changes fit the repository's supported interpreters, dependency model, and public contracts. Its configuration (`pyproject.toml`, lockfiles, the declared Python range, the CI matrix, and the configured formatter, linter, type checker, and test runner) outranks generic Python practice.

- Use only syntax and standard-library APIs that the declared minimum interpreter supports.
- The package manager, layout, formatter, type checker, test framework, and minimum Python version change only when the request changes them.
- Imports stay acyclic and follow the existing package dependency direction.
- These surfaces stay as they are unless the request changes them: import paths and exported names, call signatures, defaults and keyword names, return shapes, exception types, warnings, context-manager and iterator timing, CLI arguments, exit status, stdout and stderr, environment variables, configuration formats, serialized formats, database schemas, plugin hooks, framework callbacks, stubs and `py.typed`, and what frameworks introspect: decorator metadata, descriptors, runtime registration, signatures, and annotations.
- Sync code stays sync unless concurrency is part of the requirement.
- Ownership of files, connections, locks, tasks, and processes is visible where they are acquired, and submission, cancellation or termination, result delivery, and terminal cleanup form one lifecycle; a request to stop is not evidence that the work has settled.
- Catch an exception only where the code can recover, translate it, add boundary context, or clean up.

Read each reference that matches what the change touches:

- [Project and verification](references/project-and-verification.md): dependencies, environments, project metadata, tool configuration, tests, supported versions.
- [Types and APIs](references/types-and-apis.md): annotations, public signatures, imports, protocols, data models, decorators.
- [Errors, resources, and concurrency](references/errors-resources-and-concurrency.md): exceptions, cleanup, context managers, subprocesses, threads, processes, async code, cancellation, task lifetimes.
