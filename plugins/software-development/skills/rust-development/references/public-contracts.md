# Rust Public Contracts

Read this reference when the work touches a public Rust item or a private representation whose observable properties flow through a public item.

## Identify downstream observations

Review the contract a downstream crate can compile against, not only the edited declaration. Depending on the item, that includes:

- callable signatures, generic and lifetime bounds, inference, coercions, and conversion implementations;
- trait implementability, required items, object safety or dyn compatibility, blanket implementations, and method resolution;
- struct construction and update syntax, enum or pattern exhaustiveness, re-exports, feature gates, and platform availability;
- auto traits such as `Send`, `Sync`, and `Unpin` when callers rely on them, including properties inherited from hidden fields or opaque return types;
- associated types, iterator item and lifetime behavior, and the captures and bounds of return-position `impl Trait`.

Rust 2024 changed implicit lifetime capture for return-position `impl Trait`. Preserve the crate's edition and use an explicit `use<...>` capture only when the supported compiler and intended lifetime contract require it. A hidden concrete type remains hidden, but its promised trait bounds, captures, and downstream usability are public behavior.

Do not promise stable memory layout from ordinary field order or size observations. Treat layout as contractual only where an explicit representation, FFI boundary, or documented guarantee establishes it. Serialization and wire formats are separate contracts even when they resemble in-memory layout.

## Check compatibility at the consumer boundary

Use the repository's compatibility policy rather than assuming every source-compatible edit is semver-compatible. Changes to bounds, variants, fields, trait items, feature availability, or auto traits can break callers without changing a familiar function name.

Compile focused downstream probes for the properties at risk. Make each probe use the public crate exactly as a consumer would: build the required feature and target configuration, assert relevant trait bounds at compile time, exercise construction or matching where supported, and avoid private modules or implementation details. Pair compile probes with behavior tests when the contract includes runtime results or errors.

Primary anchors: [Cargo SemVer compatibility](https://doc.rust-lang.org/cargo/reference/semver.html), [Rust Reference: `impl Trait`](https://doc.rust-lang.org/reference/types/impl-trait.html), [Rust Reference: type layout](https://doc.rust-lang.org/reference/type-layout.html), and [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/).
