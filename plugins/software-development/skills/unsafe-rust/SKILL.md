---
name: unsafe-rust
description: "Use for unsafe Rust: unsafe blocks, fns, traits, impls, and attributes, `static mut`, extern blocks, raw pointers, MaybeUninit, FFI and layout, assembly and intrinsics, provenance and aliasing, pin projection, unsafe Send or Sync, lock-free code, and thread-affine handles. Compose with rust-development; exclude safe-only Rust."
---

# Unsafe Rust

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

Each unsafe boundary is small, necessary, and justified by invariants that safe callers cannot violate. The repository's targets, compiler and lint policy, dependencies, and existing safety documentation outrank generic unsafe practice.

You SHALL NOT use unsafe to silence the borrow checker, remove a check, or imitate an optimization until evidence supports it and a maintained safety contract covers it.

- Name the unsafe operation, why safe Rust cannot express the behavior adequately, and whether the code introduces an unchecked obligation for callers or implementors or asserts that an existing one is discharged.
- Identify which party establishes each precondition and for how long; the allocation origin, object lifetime, aliasing, alignment, initialization, and mutability rules; the unwind, panic, thread, signal, and callback boundaries; and the supported architectures, hardware features, and layout or ABI assumptions.
- Every unsafe interface, private ones included, has a written safety contract, in API documentation where callers or implementors must see it; at each unsafe block, unsafe impl, extern declaration, or unsafe attribute, keep the evidence close enough for a reviewer to connect every precondition to the fact that establishes it, with a focused `SAFETY` comment making that connection rather than restating the operation.
- Distinguish requirements enforced by types from those enforced by runtime checks, privacy, construction paths, or external contracts; if safe callers can reach undefined behavior, the abstraction is unsound even when current callers behave correctly.
- Unsafe blocks stay narrower than the surrounding algorithm, with validation and ordinary control flow in safe code where practical; the safe abstraction's constructors establish the invariant, its private state represents it, and its methods preserve it.
- Raw pointers, unconstrained lifetimes, and mutable aliases stay in the layer that needs them; never broaden visibility or weaken types for implementation convenience.
- Inside `unsafe fn` bodies, explicit unsafe blocks keep each discharged obligation visible, per the repository's `unsafe_op_in_unsafe_fn` policy.
- Check provenance, range, alignment, initialization, validity, aliasing, lifetime, and ownership for every pointer-derived access against the exact operation's contract, including zero-sized types, overflow in layout math, partially initialized state, destructors, and panic or unwind.
- Never create a reference before its validity and aliasing requirements hold; the violation happens at creation, not at dereference.
- Test at the safe boundary, including invalid inputs that must be rejected before unsafe code runs, with Miri, sanitizers, concurrency modeling, layout randomization, or target-specific tests where supported and relevant.
- Tests and dynamic tools sample executions and do not prove the contract: review the invariant against every constructor, mutation path, destructor, callback, and concurrency edge, and treat experimental aliasing models and incomplete memory-model guidance as diagnostics, not stable language guarantees.

Read every reference whose hazard is in scope; a foreign callback with concurrent or cancellable teardown needs both FFI and concurrency:

- [Pointers, validity, and initialization](references/pointers-validity-and-initialization.md): raw pointers, manual allocation or ownership, `MaybeUninit`, `UnsafeCell`, volatile access, or pointer and address conversion.
- [FFI and layout](references/ffi-and-layout.md): crossing an ABI, or `repr`, unions, variadics, callbacks, unsafe attributes, inline assembly, intrinsics, or target features.
- [Pinning and concurrency](references/pinning-and-concurrency.md): pin projection, self-reference, atomics, lock-free code, unsafe `Send` or `Sync`, or a thread-affine owner.
