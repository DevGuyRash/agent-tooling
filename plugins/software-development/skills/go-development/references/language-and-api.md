# Go Language and API Design

## Preserve the supported language contract

- Treat the module's `go` directive and CI matrix as compatibility constraints, not suggestions.
- Version-gate newer syntax and semantics, including loop-variable behavior, range forms, generic features, and standard-library additions.
- Preserve exported names, signatures, method sets, interface satisfaction, zero-value behavior, error identity, and documented side effects for public packages.
- Check downstream implementations before adding a method to an interface; that is a breaking change for every implementer.

## Model values and ownership deliberately

- Remember that arrays copy their elements, while slices and maps are descriptors over shared backing state.
- Decide whether inputs may be retained or mutated. Copy slices, maps, or byte buffers at boundaries only when the contract requires isolation.
- Distinguish nil from empty only when callers, encoders, or protocols observe the difference.
- Avoid returning internal mutable storage when callers could violate invariants.
- Do not copy a value containing `sync.Mutex`, `sync.Once`, atomics, or another no-copy field after first use.
- Keep pointer and value receivers coherent with mutation, identity, method-set, and copy costs. Do not mechanically convert every receiver.
- Make a useful zero value when it fits the type; do not force one when construction must validate a real invariant.

## Design packages and APIs

- Put interfaces near the code that consumes the behavior when practical; introduce one only for an actual substitution boundary.
- Keep interfaces as small as the consumer needs, but do not fragment a stable coherent protocol to satisfy a slogan.
- Return concrete types when callers benefit from their full behavior; preserve an existing interface-returning contract when compatibility requires it.
- Use generics when one type-safe algorithm or data structure genuinely spans types. Prefer ordinary functions or interfaces when they express the domain more clearly.
- Avoid exposing implementation types, mutable globals, or package initialization order as accidental API.
- Keep package names short and meaningful in import context; avoid stuttering only when a clearer repository-consistent name exists.
- Preserve `internal` boundaries and import-cycle freedom. Moving a type can break identity, imports, serialization names, and users.

## Handle language-specific traps

- Take the address of, capture, or store loop variables according to the module's language version; semantics changed in recent Go releases.
- Treat method values, deferred argument evaluation, typed nil interfaces, and shadowed variables as observable behavior during review.
- Keep `defer` cleanup close to acquisition, while considering loop lifetime and hot-path cost where evidence makes it relevant.
- Use `any` only when values truly have no stronger useful constraint; recover type information at a checked boundary.
- Maintain the `==` comparability requirements of map keys, generic constraints, and public types.

## Comments and style

- Run the repository's formatter rather than hand-formatting.
- Document exported contracts when the repository or lint configuration requires it.
- Explain ownership, concurrency, compatibility, protocol, and invariant decisions; omit comments that merely paraphrase code.
- Treat Effective Go and community review comments as useful background, not a complete modern specification or a license to override local style.

## Reject overbroad rules

- Do not require constructors, getters, interfaces, generics, functional options, builders, or dependency injection everywhere.
- Do not ban mutation, pointers, globals, `init`, reflection, or unsafe operations without a concrete boundary or hazard.
- Do not force every collection test into a table or every package into one preferred directory layout.

Primary references: [Go language specification](https://go.dev/ref/spec), [compatibility promise](https://go.dev/doc/go1compat), [Effective Go scope note](https://go.dev/doc/effective_go).
