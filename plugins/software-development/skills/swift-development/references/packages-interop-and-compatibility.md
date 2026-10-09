# Swift Packages, Interop, and Compatibility

Read this reference for SwiftPM manifests, module or public API changes, availability, library evolution, Objective-C/C boundaries, or multiple supported platforms.

## Preserve the package contract

Inspect the manifest's `swift-tools-version`, products, target graph, platform floors, conditional dependencies, resources, plugins/macros, unsafe flags, and test targets. Keep `Package.resolved` according to repository policy and avoid unrelated dependency refreshes. Do not raise tools/language/platform versions merely to use a convenient API without migration evidence.

Use target dependencies and conditional settings at the narrowest required scope. Avoid adding an Apple-only dependency to a target promised for Linux or Windows. Keep generated code and resources tied to their canonical regeneration/build path.

## Public API and library evolution

Review access level, overload resolution, generic constraints, conformances, enum/switch exhaustiveness, default arguments, availability, inlining attributes, and actor isolation. Source compatibility, ABI stability, and module stability are distinct promises; determine which the library actually makes. Do not add resilience or inlining attributes as generic optimization advice.

When a public signature exposes a dependency or platform type, that type becomes part of downstream source and availability constraints.

## Objective-C and C interop

For Objective-C exposure, inspect generated names, nullability, selector collisions, exception/error bridging, reference lifetime, and supported representability. For C interop, define calling convention, pointer/length relationship, mutability, ownership, allocation/free pairing, string encoding, callbacks, and thread behavior.

Do not let Swift errors or unwinding assumptions cross a foreign boundary without the established adapter. Keep foreign callbacks alive for exactly the interval allowed by their registration contract and handle late/duplicate callbacks safely.

## Platform availability

Separate compile-time availability from runtime availability. Use the repository's established guards and deployment target; a successful host build does not prove every supported platform. Keep platform-specific implementation behind existing module or conditional-compilation boundaries.

For SwiftUI/UIKit/AppKit architecture, Xcode project organization, signing, entitlements, provisioning, or App Store release behavior, follow the relevant platform workflow.

## Verification

Build affected products and tests under supported configurations. Add consumer fixtures for public or interop changes when present. Verify generated Objective-C interfaces or C consumers where contractual. Use CI for unavailable platforms and report gaps precisely.

Primary anchors: [Swift Package Manager](https://www.swift.org/package-manager/), [Swift library evolution](https://www.swift.org/blog/library-evolution/), and [Swift C++ interoperability](https://www.swift.org/documentation/cxx-interop/).
