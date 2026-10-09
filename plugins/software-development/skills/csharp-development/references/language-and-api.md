# C# Language and API Design

## Preserve the supported contract

- Treat target frameworks, `LangVersion`, nullable settings, runtime identifiers, and public API baselines as compatibility constraints.
- Version-gate syntax and BCL APIs against every supported target, not merely the installed SDK.
- For published libraries, assess source, binary, behavioral, reflection, serialization, trimming, and platform compatibility.
- Preserve overload resolution, generic constraints, optional/default values, named-argument parameter names, attributes, visibility, and documented exceptions unless the task changes them.

## Model nullability honestly

- Nullable reference annotations describe compile-time intent; they do not insert general runtime validation.
- Follow the existing nullable context.
- Validate untrusted or oblivious inputs at the boundary, then keep the internal contract precise.
- Use suppression only where an invariant is established and explain it when non-obvious; do not scatter `!` to silence warnings.
- Preserve annotations and attributes that communicate flow to callers and analyzers.

## Understand values, identity, and equality

- Distinguish reference identity, value equality, and domain equality. Keep `Equals`, `GetHashCode`, operators, and comparison contracts coherent.
- Avoid mutating fields that participate in hash or sorted ordering while an object is used as a key or member.
- Records synthesize value-oriented behavior, but `with` expressions and record copies are shallow for referenced members.
- Structs copy by value and box when used through an interface or `object`; choose them for semantic and representation reasons, not as a blanket optimization.
- Preserve `ref`, `in`, `out`, span, and ref-struct lifetime restrictions at API boundaries.

## Collections and LINQ

- Select interfaces and implementations for ordering, duplicates, mutability, concurrency, and complexity requirements.
- Account for deferred execution, multiple enumeration, captured state, provider translation, and exceptions that occur during enumeration.
- Materialize a sequence only when ownership, repeatability, snapshot, or lifetime semantics require it.
- Do not replace clear loops with LINQ or LINQ with loops solely for style.
- Treat `IQueryable<T>` as a provider contract, not an in-memory `IEnumerable<T>`; route ORM translation details to the relevant framework skill.
- Do not expose mutable internal collections when the public contract promises isolation.

## Design public APIs with restraint

- Use interfaces, abstract classes, delegates, records, discriminated-style hierarchies, or ordinary classes according to demonstrated substitution and data needs; a delegate parameter serves a one-method seam without a new type.
- Keep async, cancellation, disposal, thread-safety, ownership, and null behavior visible in signatures and documentation.
- Preserve serialization names, attribute-driven binding, reflection construction, and generated member contracts.
- Add XML documentation when repository/public API policy requires it; explain contract and reason rather than mechanics.
- Follow configured formatting and analyzer rules.

## Reject overbroad rules

- Do not require records, immutable collections, interfaces, dependency injection, result types, primary constructors, or pattern matching everywhere.
- Do not ban null, exceptions, mutable objects, inheritance, reflection, static state, or structs without a concrete hazard.
- Do not enable a new analyzer suite or rewrite repository style during an unrelated change.

Primary references: [C# language reference](https://learn.microsoft.com/dotnet/csharp/language-reference/), [nullable references](https://learn.microsoft.com/dotnet/csharp/nullable-references), [records](https://learn.microsoft.com/dotnet/csharp/fundamentals/types/records), [LINQ deferred execution](https://learn.microsoft.com/dotnet/standard/linq/deferred-execution-lazy-evaluation).
