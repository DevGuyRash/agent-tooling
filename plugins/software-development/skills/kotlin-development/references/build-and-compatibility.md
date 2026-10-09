# Kotlin Build and Compatibility

## Resolve the effective toolchain

- Prefer the repository's Gradle or Maven wrapper and declared tasks over global installations or direct compiler invocation.
- Read version catalogs, convention plugins, settings, compiler options, plugin declarations, toolchains, target settings, and CI together.
- Keep Kotlin, serialization/compiler plugins, Compose plugins, KSP/KAPT, Gradle, AGP, Java, and platform versions aligned with repository compatibility rules.
- Distinguish the JDK running the build, Java/Kotlin compile toolchains, Kotlin language/API versions, emitted JVM target, and permitted JDK API surface. Align related Java and Kotlin task targets without assuming one setting governs all five.
- Treat `.gradle.kts` as executable Kotlin DSL with Gradle lifecycle semantics; compose a Gradle/framework skill when configuration behavior is central.

## Respect source sets and targets

- Identify the owning source set before moving or adding code. Visibility and dependencies flow through the configured hierarchy.
- Keep platform-only APIs out of common source sets and preserve `expect`/`actual` coverage.
- Compile every affected target available locally; JVM success does not prove Native, JS, Wasm, or Android behavior.
- Preserve resource, cinterop, native binary, npm, and publication configuration for the relevant target.
- Route Android Gradle Plugin, manifest, resources, variants, and device behavior to an Android skill.

## Change dependencies narrowly

- Add or update only dependencies required by the task. Inspect direct, transitive, platform/BOM, catalog, lock, and metadata changes.
- Preserve configuration/source-set scope so implementation-only dependencies do not leak into public APIs.
- Change wrapper and plugin versions only as the task requires.
- Check whether an artifact supports every required target and compiler version before adding it to common code.
- Keep repositories, credentials, verification metadata, mirrors, and offline policy intact.

## Treat generated and published surfaces carefully

- Edit schema, annotated source, or generator configuration rather than generated Kotlin/Java output; regenerate through repository tasks.
- Keep KSP/KAPT ordering and generated-source registration consistent with the build.
- Inspect API dumps, explicit-API errors, binary compatibility reports, metadata, source JARs, and publication variants when library APIs change.
- Treat default-argument stubs, JVM default-interface mode, public inline bodies, parameter names used by Kotlin callers, and old precompiled consumers as compatibility surfaces even when an API dump looks unchanged.
- Preserve serialization names, reflection metadata, service descriptors, and Java-visible signatures.
- Avoid handwritten edits to wrappers, lock files, generated manifests, or API dumps unless their owning tool documents that workflow.

## Avoid environment drift

- Do not persist global Gradle, Maven, JDK, Kotlin, or native toolchain changes unless the task requires them.
- Do not assume network access or bypass dependency verification.
- Distinguish missing SDK/toolchain/dependency state from a source failure and report it accurately.
- Keep local caches and machine paths out of committed build configuration.

## Release evidence

- Build the actual artifact or target distribution, not merely an IDE compilation.
- Verify published metadata and consumer-facing signatures for libraries.
- Exercise declared platform and language-version matrices where the change crosses those boundaries.
- Report intentional compiler, plugin, target, dependency, source-set, generated, or publication changes.

Primary references: [Gradle compiler options](https://kotlinlang.org/docs/gradle-compiler-options.html), [Gradle configuration](https://kotlinlang.org/docs/gradle-configure-project.html), [evolution and compatibility](https://kotlinlang.org/docs/kotlin-evolution-principles.html), [binary compatibility validation](https://kotlinlang.org/docs/gradle-binary-compatibility-validation.html).
