---
name: typescript-development
description: Use for substantive TypeScript, TSX, declarations, compiler settings, or typed APIs. Covers modeling, narrowing, and generics; exclude JavaScript-only and Node-runtime-only work.
---

# TypeScript Development

This skill builds on the [Software Development Foundation](../../foundation.md).

TypeScript makes real program invariants visible and maintainable without standing in for runtime validation. The configuration each package and command actually uses (the effective `tsconfig` with its `extends` chain, project references, and overrides, and the repository's type-check and build commands) outranks generic practice; a root `tsconfig` the package does not use, or an ad hoc `tsc` run that selects different projects or transforms than those commands, is not evidence. Generated `.d.ts` files, transpiled JavaScript, source maps, and schema-derived types change at their source.

- Types are erased: validate network, file, environment, storage, message, and deserialized input before relying on it, and hold any value whose type is not established as `unknown` until narrowed.
- Reuse the repository's validator or parser rather than adding a second schema system; where the stack supports it, derive types from runtime schemas, or schemas from one authoritative model.
- Represent valid states directly, with discriminated unions for variants that carry different data or behavior, and keep nullable, optional, and absent properties distinct where the domain or compiler settings distinguish them.
- Confine `any` to a justified escape boundary; keep each cast or non-null assertion beside the evidence that makes it safe, and never use one to silence an incompatible API or unsafe value.
- A generic parameter relates inputs to outputs; drop one that constrains nothing, and prefer readable types to type-level computation that gives callers little or slows the compiler.
- Infer obvious locals; annotate where a type stabilizes a public contract or clarifies non-obvious intent.
- `readonly` is a static API promise, not runtime immutability; a cleaner type alone does not preserve error, mutation, ownership, or async behavior.
- Exported values and types, overloads, declaration shapes, module conditions, and generic inference are caller-facing behavior.
- A type import creates no runtime value; account for type-only imports and exports, isolated transformation, and verbatim module settings before rewriting imports.
- The module format (ESM or CommonJS) and compiler-wide strictness stay unless the task owns that migration.
- A clean type check is not runtime execution: when the supported runtime runs emitted JavaScript, loader or transform output, or native TypeScript syntax, exercise that path.
- Check a changed public type or package boundary against its consumers, from a packed or external fixture where internal path aliases could hide declaration or export defects.
- Know whether compatibility means one frozen install and configuration or a moving matrix of compiler, resolver, runtime, dependency, and package-export versions.

Read each reference that matches what the change touches:

- [Type modeling](references/type-modeling.md): unions, narrowing, generics, optionality, assertions, mapped or conditional types.
- [Boundaries and APIs](references/boundaries-and-apis.md): parsing, type guards, exported types, declarations, compatibility, interop.
- [Compiler and verification](references/compiler-and-verification.md): before changing compiler settings, package declarations, build integration, or compatibility targets.
