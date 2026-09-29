---
name: php-development
description: >-
  Use for substantive PHP source, Composer, or tooling. Covers types, APIs, errors, resources, and security-sensitive behavior; exclude framework-only work.
---

# PHP Development

PHP changes fit the repository's supported runtime, SAPIs, extensions, Composer graph, public contracts, and framework lifecycle. Its declared PHP and `ext-*` requirements, `composer.json` and `composer.lock` (autoload, scripts, plugins, `config.platform`), CI matrix, deployment SAPI, loaded extensions, `php.ini` behavior, and existing namespace, autoload, bootstrap, and framework lifecycle decisions outrank generic practice. PSR/PER interoperability and framework conventions bind only where the repository selects them; they are not PHP language policy.

- Use only syntax and APIs the declared minimum PHP version and required extensions support.
- The minimum PHP version, framework, package layout, style standard, analyzer, test runner, and dependency policy change only when the request changes them.
- Follow the repository's `declare(strict_types=1)` policy; do not add it mechanically to legacy files.
- Use accurate native declarations where supported, and PHPDoc only for analyzer information PHP cannot express.
- Make scalar coercion, array-key normalization, missing-versus-null, and comparison semantics explicit at trust and public API boundaries.
- Prove a required field present with `array_key_exists()` before reading, defaulting, normalizing, or inserting it; never silently turn missing into present-null or skip the invalid record unless that is the declared contract.
- Use references only for intentional aliasing, not as a presumed optimization, and end each by-reference iteration's lease explicitly.
- Catch only where the code can recover, translate, add boundary context, or clean up.
- Make ownership of streams, locks, transactions, temporary files, processes, and long-lived services visible.
- Progress every owned pipe of a child process without deadlock, bound the wait, and keep termination request, process exit, pipe completion, reaping, and descendant ownership distinct.
- These stay as they are unless the request changes them: namespaces, class names, Composer autoload paths, public constants, properties, and visibility; parameter names (named arguments make them observable), positions, defaults, by-reference behavior, variadics, native and PHPDoc types, and return values; inheritance variance, interfaces, traits, attributes, magic methods, and reflection-visible metadata; exceptions, warnings, deprecations, resource ownership, serialization, and framework hooks; observed array keys, shapes, ordering, missing-versus-null distinctions, reference aliasing, and interior object mutation; CLI arguments, exit status, streams, environment and configuration, HTTP messages, and database behavior.
- After a Composer metadata or lock change, run Composer validation and check lock consistency deliberately.
- When distribution files, autoloading, or package metadata change, build or inspect the package artifact.
- When PHP, extension, SAPI, or deployment compatibility changes, check the platform requirements against the actual runtime; a run with ignored platform requirements is not success evidence.

Read each reference that matches what the change touches:

- [Project and verification](references/project-and-verification.md): PHP versions, SAPIs, Composer, extensions, dependencies, project metadata, tests, verification.
- [Types and public APIs](references/types-and-public-apis.md): `strict_types`, coercion, declarations, PHPDoc, public signatures, named arguments, inheritance, compatibility.
- [Errors, resources, and security](references/errors-resources-and-security.md): `Throwable`, error handling, cleanup, streams, transactions, workers, serialization, SQL, output encoding, secrets, untrusted input.
- [Interoperability and style](references/interoperability-and-style.md): PSR/PER decisions, autoload interoperability, shared interfaces, formatting, comments, framework boundaries.
