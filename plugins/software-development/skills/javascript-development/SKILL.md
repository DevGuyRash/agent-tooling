---
name: javascript-development
description: Use for substantive JavaScript, JSX, or JSDoc/checkJs work. Covers modules, promises, mutability, and prototypes; exclude TypeScript-only and Node-runtime-only work.
---

# JavaScript Development

JavaScript changes fit the repository's language level, runtimes, module system (ESM or CommonJS, as `package.json`, file extensions, and bundler configuration set it), package manager, and tools. Generated, vendored, and compiled output changes at its source.

- Choose `??` or `||` from what a falsy value means in the domain, and keep missing, `undefined`, and `null` distinct where callers can see the difference.
- Use strict equality by default, keeping a deliberate coercive comparison only where its contract is clear and tested.
- Choose arrays, objects, `Map`, and `Set` for their key, ordering, identity, and serialization semantics.
- Copies and adapters keep prototypes, descriptors, symbols, and class identity.
- Iteration order, sort stability, and locale-sensitive comparison are observable when output depends on them.
- Every promise is awaited or deliberately returned; background work stays observable and its rejections are handled.
- Bound concurrency where work is admitted, before it is invoked: a promise that exists is already running, and wrapping it restores no bound.
- Aggregate settlement, a cancellation request, an observed timeout, and completion of owned work are separate events; a race or an early rejection does not stop the losing work.
- Error identity and `cause` stay intact where callers inspect them, and listeners, timers, and subscriptions are removed on success, failure, and cancellation.
- Exported names, default versus named exports, module side effects, package entry points, and import timing are public behavior, and the module system stays as it is unless the request changes it; dependencies, transpilation targets, and tooling change only for a task-specific reason, and environment-specific APIs stay behind an explicit boundary when code runs in more than one runtime.

Read each reference that matches what the change touches:

- [Language and modules](references/language-and-modules.md): values, objects, compatibility, module loading.
- [Async, errors, and APIs](references/async-errors-and-apis.md): promises, cancellation, event APIs, resource lifetime, error contracts.
- [Testing and tooling](references/testing-and-tooling.md): choosing tests, changing dependencies or build targets, tool disagreement.
