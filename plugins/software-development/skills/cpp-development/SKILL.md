---
name: cpp-development
description: Use for substantive C++ source, build-classified headers, or tooling. Covers RAII, templates, undefined behavior, ABI, and errors; exclude C-only work.
---

# C++ Development

C++ changes keep ownership, lifetime, error, ABI, and compilation contracts explicit. The repository's standard and accepted extensions, compiler and standard-library matrix (families, minimum versions, targets), warnings and sanitizers, build system, ownership, exception, RTTI, allocation, threading, and error conventions, and public API, ABI, visibility, and module or header promises outrank generic C++ practice; the standard, compiler floor, dependencies, warning policy, exception and RTTI mode, and ABI change only when the request changes them.

- The compiler invocation and a `.cc`, `.cpp`, `.cxx`, or module file outrank syntax resemblance; classify a `.h` file from compile commands, build targets, includers, language flags, and compatibility requirements, not its extension, and keep a C API header that C++ also consumes valid C.
- Values hold independent value-like state and RAII owners hold resources; choose `unique_ptr`, `shared_ptr`, weak observation, or a raw non-owner from the actual ownership graph, never by replacing every pointer mechanically.
- Use references, pointers, spans, views, and iterators as non-owning vocabulary only where their valid lifetime and nullability are clear; never return or store a view into a temporary, a moved-from object, a reallocated container, or an owner whose lifetime is not tied to the view.
- Interfaces stay narrow and make ownership transfer visible; a move is a state transition whose valid post-move use is documented where callers depend on it.
- Declare `noexcept` only where the operation satisfies it; termination caused by a false declaration is observable behavior.
- Destructors and cleanup paths stay safe during partial construction and stack unwinding where exceptions are enabled.
- With binary consumers, public type layout, inline definitions, virtual tables, name mangling, calling convention, allocator ownership, exception propagation, and standard-library types are ABI; implementation details stay out of public headers unless that compile-time or ABI coupling is intended, and the repository's export macros, visibility, module boundaries, and explicit-instantiation strategy hold.
- Prefer standard algorithms and library types where supported and clearer than handwritten control flow; templates, concepts, inheritance, type erasure, and metaprogramming need a real variation or constraint boundary, not anticipated hypothetical implementations.
- Build every impacted configuration and compiler and standard-library variant available, C consumers of a shared header included.
- Tests reach the construction-failure, destruction, copy and move, empty and boundary, iterator and view invalidation, exception or error, and concurrency cases the change touches; run configured static analysis and sanitizers for lifetime, race, and undefined-behavior risks, and treat a clean run as evidence, not proof.

Read [ownership and lifetimes](references/ownership-and-lifetimes.md) for ownership transfer, views, iterators, callbacks, moves, RAII, exceptions, concurrency, or lifetime failures, and [templates, ABI, and build](references/templates-abi-and-build.md) for templates, concepts, public headers or modules, ODR, linkage, shared libraries, ABI, or build configuration.
