---
name: python-development
description: >-
  Use for Python source, stubs, or pyproject tooling: typing, imports, exceptions, resources, asyncio, threads, processes, and subprocesses. Excludes conceptual Q&A, throwaway one-liners, and publication-only work.
---

# Python Development

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Python code fits the repository's supported interpreters, dependency model, and public contracts. Its configuration (`pyproject.toml`, lockfiles, the declared Python range, the CI matrix, and the configured formatter, linter, type checker, and test runner) outranks generic Python practice.

- Use only syntax and standard-library APIs that the declared minimum interpreter supports.
- The package manager, layout, formatter, type checker, test framework, and minimum Python version change only when the request changes them.
- Imports stay acyclic and follow the existing package dependency direction; a module-level import cycle runs code against a partially initialized module.
- These surfaces stay as they are unless the request changes them: import paths and exported names, call signatures, sync or async call shape, defaults and keyword names, return shapes, exception types, warnings, context-manager and iterator timing, CLI arguments, exit status, stdout and stderr, environment variables, configuration formats, serialized formats, database schemas, plugin hooks, framework callbacks, stubs and `py.typed`, and what frameworks introspect: decorator metadata, descriptors, runtime registration, signatures, and annotations.
- Membership tests on a `list` or `tuple` scan it, while `set` and `dict` hash.
- Iterating a generator or file holds one item at a time, while `list()`, `read()`, or `readlines()` holds all of it.
- Independent waits overlap as `asyncio` tasks in asynchronous code and on a `concurrent.futures` thread pool in synchronous code.
- `asyncio.gather` over every item starts every wait at once, so an `asyncio.Semaphore` or a fixed set of worker tasks holds the shared limit.
- A thread pool's `max_workers` bounds the calls running at once, while `Executor.map` and a loop that submits every item queue all of them in memory.
- Blocking calls in asynchronous code run through `asyncio.to_thread` or an executor, off the event loop.
- In the default CPython build, threads overlap waiting but not Python computation.
- Python computation spreads across cores through processes.
- The interpreter lock is no synchronization contract.
- Ownership of files, connections, locks, tasks, and processes is visible where they are acquired, and submission, cancellation or termination, result delivery, and terminal cleanup form one lifecycle; a request to stop is not evidence that the work has settled.
- Context managers such as `with`, `async with`, `contextlib.ExitStack`, and `asyncio.TaskGroup` give files, connections, locks, tasks, and processes an owner that releases them on every exit.
- `cancel()` and `terminate()` only request an end, and a timeout exception only reports that a wait gave up; awaiting, joining, or reaping the work shows that it ended.
- Catch an exception only where the code can recover, translate it, add boundary context, or clean up.
- A translated exception keeps its cause through `raise ... from`.
- A bare `except` or `except BaseException` also catches cancellation and interpreter exit.

Read each reference that matches the task:

- [Project and verification](references/project-and-verification.md): dependencies, environments, project metadata, tool configuration, tests, supported versions.
- [Types and APIs](references/types-and-apis.md): annotations, public signatures, imports, protocols, data models, decorators.
- [Errors, resources, and concurrency](references/errors-resources-and-concurrency.md): exceptions, cleanup, context managers, subprocesses, threads, processes, async code, cancellation, task lifetimes.
