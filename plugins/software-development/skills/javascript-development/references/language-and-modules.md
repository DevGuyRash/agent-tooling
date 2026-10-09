# JavaScript Language and Modules

Load this reference for value semantics, data structures, compatibility decisions, imports, exports, or module migrations.

## Values and Control Flow

- Distinguish `null`, `undefined`, absent properties, empty strings, zero, `NaN`, and `false` whenever the domain distinguishes them.
- Distinguish own properties from inherited properties as well as from an own value of `undefined`; choose property access, `in`, or an own-property test from the boundary contract and supported target.
- Use `??` for a nullish fallback and `||` for a falsy fallback. Replacing one with the other is a behavior change.
- Use optional chaining only when absence is accepted. It can hide a broken invariant if a value is required.
- Prefer explicit numeric parsing and validation at input boundaries. JavaScript coercion, `NaN`, infinities, and floating-point precision can escape otherwise reasonable checks.
- Remember that object equality is identity equality. Define value comparison deliberately when the domain needs it.

## Objects and Collections

- Use plain objects for record-like string/symbol-keyed data that must interoperate with object syntax or JSON.
- Use `Map` when keys are not naturally property names, insertion order or key identity matters, or entries are frequently added and removed.
- Use `Set` when uniqueness is the contract, not merely as an unexplained deduplication step.
- Treat shallow spread as shallow. It does not preserve prototypes, accessors, non-enumerable properties, or nested ownership.
- Treat structured cloning or serialization as an explicit transfer contract, not a general rich-object copy; custom prototypes, descriptors, functions, private state, identity, and transfer behavior may differ.
- Avoid mutating objects received from callers unless mutation is part of the API. Avoid cloning when identity itself is contractual.
- Supply a comparator for numeric or domain-specific sorting. Add a deterministic tie-breaker when stable external output depends on it.

## Functions and Classes

- Use closures, functions, or classes according to existing architecture and lifecycle needs.
- Do not convert methods to arrow properties or vice versa without checking `this`, prototype identity, mocking, inheritance, and allocation behavior.
- Keep callbacks small enough that return, throw, and async behavior remain visible.
- Prefer parameter objects only when they improve evolution or call-site meaning; they are not automatically clearer for small stable signatures.

## Modules

- Derive semantics from file extensions, nearest `package.json` `type`, exports/imports maps, compiler or bundler settings, and the target runtime.
- Preserve live import/export bindings, instantiation and evaluation order, and side effects when reorganizing modules; a copied value or wrapper export can change the contract.
- Account for cycles and uninitialized bindings before moving initialization across modules. Top-level asynchronous evaluation can propagate through importers and introduces runtime-support and cycle/liveness questions that require executable tests.
- Avoid deep imports into another package unless that path is an explicit supported export.
- Treat default/named export changes and package-condition changes as compatibility changes.
- Keep browser, worker, server, and test-only dependencies from leaking across runtime boundaries.
- Remember that module instances and globals are scoped to a host realm/cache. Cross-realm constructor identity, `instanceof`, registered versus local symbols, and repeated-import state are observable when APIs cross that boundary.

## Compatibility

- Select syntax and built-ins from the declared runtime/browser matrix, not the newest locally installed engine.
- Distinguish syntax transpilation from missing runtime APIs; the latter may require a polyfill or different implementation.
- Do not add a polyfill globally without checking bundle size, realm behavior, and host conflicts.
- Preserve repository-selected Babel, SWC, bundler, minifier, and module-resolution behavior unless the task requires changing it.

Primary semantic authority: [ECMAScript Language Specification](https://tc39.es/ecma262/). Runtime compatibility still comes from the repository's supported target documentation and tests.
