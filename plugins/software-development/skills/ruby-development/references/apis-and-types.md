# APIs and Types

Read this reference for method signatures, keywords, blocks, constants, metaprogramming, RBS, Sorbet, or public compatibility.

## Preserve Ruby call semantics

Ruby 3 separates positional hashes from keyword arguments. Treat parameter kind and forwarding as behavior:

- Preserve positional, optional, rest, keyword, required-keyword, keyword-rest, and block parameters.
- Use `...` or explicit forwarding only when supported by the minimum Ruby and compatible with introspection needs.
- Keep legacy `ruby2_keywords` behavior only where the supported range and delegation contract require it.
- Keep public keyword names; callers may bind them by name.

Blocks also form API. Preserve whether a method requires a block, yields values, returns an Enumerator without one, forwards the block, performs non-local control flow, or retains the block beyond the call.

A delegator can preserve successful calls while changing `Method#parameters`, arity, source ownership, visibility, or `respond_to?`. Determine which reflective surfaces consumers use. Prefer an explicit public signature when names and parameter kinds are contractual; use generic forwarding when transparent acceptance matters and generic reflection is acceptable. Test the unbound and bound method when both are public surfaces.

## Preserve value and key contracts

`==`, `eql?`, `hash`, ordering, and pattern/deconstruction methods serve different protocols. When value objects are hash or set keys, ensure `a.eql?(b)` implies `a.hash == b.hash`, include the same identity fields in both, and preserve the repository's class/subclass policy. Keep identity fields stable while an object is an active key; prefer immutable key state over requiring every owner to call `rehash` after mutation. Test equivalent distinct instances, unequal instances, lookup, deduplication, and mutation boundaries.

## Protect public surfaces

Consider require paths, constants, method visibility, inheritance hooks, mixin order, refinements, callbacks, and monkey patches. Public behavior may include mutability, object identity, ordering, laziness, and exceptions.

When using `method_missing`, implement compatible discovery such as `respond_to_missing?` and preserve forwarding. Prefer ordinary methods when the dynamic surface is finite and known. Avoid changing global core classes for local convenience.

## Use typing by repository contract

RBS, Steep, Sorbet RBI, inline annotations, and runtime validation are distinct systems. Inspect generated-file ownership and the configured checker before editing signatures.

- Keep implementation, checked signatures, and published gem artifacts aligned.
- Model useful public boundaries and complex internal contracts.
- Preserve nilability, block types, generics, overload behavior, and variance expected by the selected system.
- Use escape hatches narrowly and explain non-obvious checker limitations.
- Do not introduce a second type system or convert generated signatures by hand.

Duck typing, modules, concrete classes, data objects, Struct, and framework models are all valid. Choose from repository needs, not a universal architecture.

## Document durable behavior

Follow the project's RDoc, YARD, or plain-comment convention. Document public behavior, side effects, raised exceptions callers handle, mutation, thread safety, and non-obvious constraints. Avoid narrating Ruby syntax or promising private implementation details.
