# C++ Templates, ABI, and Builds

Read this reference when the work touches templates, concepts, headers/modules, ODR, linkage, libraries, exported types, or build flags.

## Template and constraint design

Use templates when behavior must vary by type at compile time and the supported toolchain can express the contract clearly. Constrain operations callers actually need. Prefer diagnostics that identify an unmet interface rather than letting substitution fail deep in an implementation. Avoid encoding runtime variation into template parameters solely for perceived performance or style.

Decide where definitions and instantiations live. Keep explicit instantiation, export visibility, and supported type sets aligned with the build system. Changes to constraints, overload sets, defaults, deduction guides, hidden friends, and specialization can alter source compatibility or overload resolution even when signatures look similar.

## ODR and compilation boundaries

Headers must be valid in every supported translation unit that consumes them and must not introduce unintended definitions or macro state. Inline variables/functions, templates, and modules still carry One Definition Rule obligations across configurations. Keep compile definitions that affect public layout or inline behavior consistent among producers and consumers.

For `.h`, classify from actual compiler/includer evidence. Verify intentionally shared C headers under both C and C++ compilers.

## ABI

When binary consumers exist (a promised stable ABI, or binaries not rebuilt together), review exported names, calling conventions, object layout, base classes, virtual functions, RTTI, exception behavior, alignment, allocator boundaries, and standard-library types in exported signatures. A source-compatible edit may still break ABI.

Use the project's established PImpl, opaque handle, symbol-versioning, or ABI-checking approach where binary consumers exist.

Treat the declared target platform, compiler, standard library, runtime, and build flags—and their matching ABI documentation and tools—as authoritative.

## Build configuration

Preserve the selected standard, compiler/stdlib matrix, exception and RTTI flags, visibility, link mode, runtime library, sanitizers, and warning policy. Do not fix one target by adding global flags that alter every consumer. Generated code and modules must retain their canonical dependency-scanning and regeneration path.

## Verification

Build affected translation units and link final consumers, not only compile a header in isolation. Exercise supported configurations and compiler/stdlib variants. Where ABI is promised, use the repository's ABI comparison tooling or consumer fixtures and report any unavailable platform matrix.

Primary anchors: [ISO C++ standard information](https://isocpp.org/std/the-standard), [C++ Core Guidelines: templates](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#S-templates), and the selected compiler's ABI documentation.
