# C ABI and Portability

Read this reference for public headers, FFI, libraries, layout-sensitive representations, multiple compilers/operating systems, or cross-language consumers.

## Define the target matrix

Record the supported C standard baseline, compiler families and minimum versions, architectures/data models, operating systems, libc implementations, endianness, and build modes. Separate ISO C requirements from compiler extensions and project policy. A construct accepted by one compiler under its default dialect is not automatically portable C.

## Public headers

Make headers self-contained under the repository's include policy. Use include guards or supported equivalents consistently. Do not leak private macros, compiler flags, dependency headers, packing state, or platform types into public consumers unintentionally.

For headers consumed by C++, verify the actual declarations under a C++ compiler and use the project's `extern "C"` boundary. C compatibility does not imply C++ source compatibility, nor the reverse.

Keep feature-test macros and configuration headers ordered as required by the platform. Avoid defining reserved identifiers.

## ABI and layout

Treat exported symbol names, calling conventions, parameter/return types, type size/alignment, field offsets, enum representation, ownership, and allocator choice as ABI contracts when binary consumers depend on them. Opaque handles reduce layout coupling when consumers do not need representation access.

Do not serialize a native struct by dumping its bytes unless padding, byte order, widths, versioning, and validity are explicitly part of the format. Use explicit encode/decode routines for durable or network formats. Packed structs may produce unaligned members and compiler-specific layout; use them only under a documented target contract.

## Platform APIs and build flags

Keep OS/compiler-specific code behind the repository's existing configuration boundary. Pair feature detection with the build system rather than inferring capability from platform names when possible. Warning flags, sanitizer flags, linker options, and extensions differ between compilers; preserve target-scoped configuration.

Do not hardcode `long`, pointer, `time_t`, `off_t`, or `size_t` widths. Use exact-width types only when the external format requires an exact width and the implementation provides it.

## Verification

Build public headers as C and through supported foreign consumers. Exercise shared/static variants and visibility/export configuration where those are products. Validate representation with compile-time assertions only for contractual facts. Run cross-target CI; report compilers and architectures it lacks rather than extrapolating from the host.

Primary anchors: [ISO C working group](https://www.open-std.org/jtc1/sc22/wg14/), [GCC C implementation-defined behavior](https://gcc.gnu.org/onlinedocs/gcc/C-Implementation.html), and [Clang language compatibility](https://clang.llvm.org/compatibility.html).
