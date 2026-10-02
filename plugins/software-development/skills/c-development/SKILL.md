---
name: c-development
description: "Use for C source, build-classified headers, or tooling: ownership, bounds, undefined behavior, threads, ABI, and errors. Excludes C++-only work."
---

# C Development

This skill builds on the [Software Development Foundation](../../foundation.md).

C code keeps ownership, bounds, lifetime, ABI, and failure contracts explicit. The repository's C standard and permitted extensions, target matrix (compilers, architectures, data models, endianness), warning policy, build system, binary-compatibility promises, and allocator, ownership, threading, error, logging, and cleanup conventions outrank generic C practice; the standard, compiler floor, dependencies, warnings, and ABI change only when the request changes them.

- The compiler invocation and a `.c` extension outrank syntax resemblance; classify a `.h` file from compile commands, build targets, includers, `extern "C"` use, and compatibility requirements, not its extension, and keep a header that C and C++ both consume valid in both.
- Each resource has one identifiable owner and one release contract, with allocation and deallocation families paired; where types cannot say so, document whether a parameter or returned pointer is borrowed, transferred, retained, nullable, counted, or NUL-terminated.
- Initialize state before any failure path can inspect or release it, release partially acquired resources through a single cleanup path (`goto cleanup` included) where that makes them visibly correct, and let control flow and local state prevent reuse after transfer or release.
- Validate sizes before allocation, multiplication, addition, narrowing, pointer movement, and indexing; a successful allocation does not prove the size calculation valid.
- Signedness, integer promotions, shifts, overflow, and sentinel conversions are semantic decisions.
- Byte counts stay distinct from element counts, the terminating NUL is counted only where the representation requires one, and length-aware operations are the ones whose truncation and termination behavior is understood on every target.
- Follow the repository's status-code, `errno`, out-parameter, nullable-result, or structured-error convention: check return values that affect correctness, capture transient error indicators before another call overwrites them, leave outputs and resources in their documented state on every failure path, and never log and continue where the caller contract requires propagation or rollback.
- Assume nothing about pointer width, `char` signedness, alignment, byte order, structure padding, or atomic lock-freedom; fixed-width integers are for exact-width external representations, not a replacement for natural size types.
- Compiler extensions, pragmas, attributes, packed layouts, VLAs, and platform APIs follow the declared target matrix; compile every impacted target and configuration available, C++ consumers of a shared header included.
- Reference counting, global singletons, and wrapper layers need a real ownership problem.
- C overlaps waits with the repository's threads or with nonblocking descriptors on the platform's readiness interface, such as `poll`.
- C spreads computation across cores with threads.
- Tests reach the empty, maximum, malformed, partial-failure, allocation-failure, aliasing, and cleanup cases the change touches; run configured static analysis, sanitizers, and fuzzers on high-risk paths, knowing a clean run samples behavior and does not prove undefined behavior absent.

Read [ownership and undefined behavior](references/ownership-and-undefined-behavior.md) for pointer arithmetic, allocation, buffers, ownership transfer, concurrency, parsing, or suspected undefined behavior, and [ABI and portability](references/abi-and-portability.md) for public headers, FFI, shared libraries, struct layout, wire or file formats, or compiler and OS portability.
