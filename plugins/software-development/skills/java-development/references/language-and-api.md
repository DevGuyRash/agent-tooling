# Java Language and API Design

## Preserve the supported contract

- Treat configured source, `--release`, bytecode, runtime, and library targets as distinct compatibility dimensions.
- Version-gate records, sealed types, pattern matching, switch forms, `var`, and newer library APIs against the effective build configuration.
- For published libraries, assess source, binary, behavioral, serialization, and reflective compatibility; a compiling producer does not prove existing consumers still link.
- Preserve overload resolution, generic signatures, annotations, visibility, inheritance, service contracts, and documented exceptions unless change is intentional.

## Model identity, equality, and mutability

- Keep `equals` and `hashCode` consistent; maintain `compareTo` consistency when sorted collections depend on it.
- Do not mutate fields that participate in hash or ordering while an object is a key or sorted member.
- Remember that records synthesize value-oriented members from components, but components and `with`-like reconstruction patterns are not deep immutability.
- Make defensive copies at ownership boundaries when callers must not mutate internal state; avoid copying by reflex when aliasing is part of the contract.
- Distinguish unmodifiable views from immutable snapshots and document the behavior callers observe.
- Prefer primitives where absence and identity are irrelevant, while preserving nullable or boxed public contracts.

## Use types and generics deliberately

- Preserve generic variance and wildcard behavior. Use bounds to express a real producer/consumer relationship, not to satisfy a slogan.
- Avoid raw types and unchecked casts; when interop requires one, isolate it and validate the assumption at the boundary.
- Define an interface for a genuine substitution boundary. Do not create an interface, implementation, factory, and injector for every class.
- Keep type parameters meaningful and minimal. A duplicated two-line method is not automatically a generic framework.
- Treat nullness annotations as repository/tool-specific contracts. They improve analysis but do not add universal runtime checks.
- Never return or accept a null `Optional`. Use `Optional` where absence is part of the API and existing conventions support it; do not force it into every field, parameter, or collection.

## Collections, streams, and control flow

- Select collection interfaces and implementations for ordering, duplicates, null policy, concurrency, and complexity requirements.
- Account for stream laziness, single-use traversal, encounter order, side effects, and resource ownership.
- Do not replace a clear loop with a stream or a stream with a loop solely for style.
- Use `java.util.Objects` helpers where they preserve the intended null and equality semantics, not as automatic rewrites.
- Treat Java `assert` as development-time checking that may be disabled; do not use it for public input validation or required side effects.

## Public API and documentation

- Minimize exported surface, but preserve already supported constructors, methods, constants, and extension points.
- Document nullability, ownership, thread safety, blocking, side effects, exceptions, and lifecycle when consumers cannot infer them.
- Check serialization identifiers and shapes before changing `Serializable`, records, JSON-bound types, or reflective construction.
- Keep comments focused on contract and reason. Follow configured Javadoc and style tooling rather than imposing a community guide.

## Reject overbroad rules

- Do not require records, builders, factories, getters, setters, streams, immutability, or dependency injection everywhere.
- Do not ban inheritance, mutable objects, null, reflection, or static state without a concrete compatibility or correctness hazard.
- Do not adopt a new nullness, functional, collection, or annotation library merely to make a local change look modern.

Use the language and API documentation edition that matches the repository's effective target JDK. Primary references: [Java Language Specification index](https://docs.oracle.com/javase/specs/jls/) and [Java API specification index](https://docs.oracle.com/en/java/javase/).
