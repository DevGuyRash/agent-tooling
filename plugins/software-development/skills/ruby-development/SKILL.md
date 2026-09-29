---
name: ruby-development
description: >-
  Use for substantive Ruby source, gems, Bundler, or tooling. Covers dynamic behavior, APIs, errors, resources, concurrency, and tests; exclude Rails-only work.
---

# Ruby Development

Ruby changes fit the repository's supported interpreters, dependency graph, framework boundaries, and public behavior. Its `.ruby-version` and version-manager files, `Gemfile`, lockfile, gemspecs, Bundler configuration, `required_ruby_version`, CI matrix, deployment runtime, native-extension constraints, load paths, autoloading, and framework lifecycle outrank generic practice and any preferred style stack.

- Use only syntax and core APIs the declared minimum Ruby supports; the local Ruby alone does not show compatibility.
- Bundler, the test framework, RuboCop or Standard, RBS or Sorbet, the package layout, and the minimum Ruby version change only when the request changes them.
- Run tools through the project's Bundler or task-runner interface when that is its contract.
- Load order, autoloading, constant resolution, and dependency direction stay consistent with the project.
- Monkey patches, shared constants, callbacks, and autoloading reach every caller in the process, so their changes are tested at that scope.
- Prefer direct objects, messages, collections, and blocks; add abstraction or metaprogramming only for a demonstrated contract or repeated variation.
- Positional arguments, keywords, splats, keyword splats, and blocks stay distinct.
- Follow the repository's mutation and bang-method conventions; a method name's punctuation alone does not show that it is safe.
- Use the established typing system only where it improves a real boundary.
- Rescue only where the code can recover, translate, add boundary context, retry deliberately, or clean up.
- Make ownership of files, sockets, transactions, locks, threads, and subprocesses explicit.
- These stay as they are unless the request changes them: require paths, constants, autoload names, visibility, inheritance, and refinement scope; method names, positional and keyword parameters, defaults, block requirements, and return values; Enumerator behavior when no block is given, laziness, mutation, identity, equality, and ordering; exception classes, messages when asserted, callbacks, hooks, and framework conventions; CLI arguments, exit status, stdout and stderr, environment variables, serialized forms, and gem metadata.
- When the gemspec, executables, packaged files, or package metadata change, build and inspect the gem.

Read each reference that matches what the change touches:

- [Project and verification](references/project-and-verification.md): Ruby versions, Bundler, gems, dependencies, native extensions, project metadata, verification.
- [APIs and types](references/apis-and-types.md): public methods, keyword arguments, blocks, equality and hash behavior, constants, metaprogramming, signatures, RBS, Sorbet, compatibility.
- [Errors, resources, and concurrency](references/errors-resources-and-concurrency.md): exceptions, cleanup, transactions, queues, threads, processes, Fibers, Ractors, timeouts, cancellation, long-running workers.
- [Security and framework boundaries](references/security-and-framework-boundaries.md): commands, serialization, templates, SQL, paths, secrets, dynamic dispatch, Rails or another framework.
