# TypeScript Boundaries and APIs

Load this reference for untrusted input, runtime validation, declarations, public types, JavaScript interop, or compatibility-sensitive API changes.

## Runtime Boundaries

- Treat network responses, request bodies, files, environment variables, local storage, database rows, message queues, and parsed JSON as untrusted until validated or parsed.
- Validate at the point where external data becomes an internal invariant.
- Transform input during parsing when normalization is part of the boundary contract; do not hide lossy conversion inside a type assertion.
- Include actionable path/context in validation failures without exposing secrets or sensitive payloads.

## Assertions and Escape Hatches

- Tie each non-null assertion or cast to a nearby invariant, prior check, framework guarantee, or testable construction.
- Contain unsafe third-party declarations in a small adapter rather than spreading casts through consumers.
- Use `unknown` at uncertain boundaries and `any` only where interoperability genuinely prevents meaningful checking.
- Fix inaccurate local declarations or provide a scoped augmentation when the runtime API is known and stable.
- Do not globally weaken compiler checks to accommodate one dependency or generated surface.

## Public API Design

- Treat exported types and inferred declaration output as versioned API when another package or user consumes them.
- Prefer named domain types at public boundaries when they improve diagnostics and compatibility review.
- Keep implementation-only fields out of exported structural types.
- Consider both accepted inputs and inferred outputs when changing overloads, defaults, generic constraints, or optional fields.
- Preserve useful inference and avoid exposing a type that depends on private or unstable implementation details.
- Review emitted declarations when declaration generation is part of the package contract.

## JavaScript and Library Interop

- Respect `allowJs`, `checkJs`, JSDoc types, declaration files, and package export conditions selected by the repository.
- Treat edits to JavaScript/JSDoc runtime source as JavaScript work even when `checkJs` analyzes it; TypeScript owns the effective compiler configuration, declarations, project graph, and typed-consumer contract.
- Use type-only imports when required by the configured transform; do not rewrite imports without checking runtime emission.
- Verify whether a dependency's declarations match the installed runtime version before compensating locally.
- Keep ambient declarations narrowly scoped. A global augmentation can affect every consumer in the compilation.
- For dual-runtime or dual-module packages, test the actual public import paths rather than only internal source imports.
- Test emitted declarations from an external consumer when public inference, resolution, or package exports matter; compiling only the source project can hide private paths and workspace-only resolution.

Types can prevent representable mistakes; they do not replace authorization, validation, synchronization, or runtime tests.
