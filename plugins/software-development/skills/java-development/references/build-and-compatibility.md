# Java Build and Compatibility

## Use the repository build

- Prefer `mvnw` or `gradlew` and repository tasks over a globally installed Maven or Gradle version.
- Read parent POMs, convention plugins, settings, version catalogs, toolchains, and CI before invoking low-level compiler commands.
- Do not manually edit wrapper JARs, generated wrapper metadata, dependency locks, or generated source.
- Preserve offline, proxy, mirror, repository, credential, and cache policy; do not bypass integrity checks to make resolution pass.

## Resolve JDK and bytecode targets

- Distinguish the JDK running the build from the Java language level, `--release` API surface, emitted bytecode, and supported runtime.
- Prefer the repository's toolchain configuration, and compile only against APIs the declared runtime provides.
- Treat annotation processors, compiler plugins, preview features, and `--enable-preview` as compile-and-runtime contracts.
- Check mixed-language source sets and generated stubs when Java interoperates with Kotlin, Scala, Groovy, or native code.

## Change dependencies narrowly

- Add or update only dependencies required by the task. Inspect direct, transitive, platform/BOM, scope/configuration, and lock changes.
- Preserve dependency constraints, exclusions, optionality, classifiers, and platform variants unless the task revises them.
- Check split packages, duplicate classes, service providers, shading/relocation, and licensing when packaging behavior changes.
- Keep test-only tools out of runtime artifacts and avoid leaking implementation dependencies into published APIs.

## Respect modules and runtime packaging

- When JPMS is active, preserve exported/opened packages, required modules, service uses/providers, and reflective access.
- Distinguish classpath from module-path behavior. A classpath-only test does not prove a modular runtime.
- Treat automatic module names and module descriptors as public compatibility surfaces for published artifacts.
- Preserve manifest entries, main classes, service files, multi-release JAR layout, native resources, and reproducible-build settings.
- Check container or deployment runtime separately when its JRE image, architecture, or flags differ from development.

## Generated and reflective surfaces

- Edit the schema, template, or annotated source that owns generated output; regenerate through the repository command.
- Preserve reflection configuration, serializers, dependency-injection metadata, service loaders, and native-image hints when they are in scope.
- Route framework-specific generated behavior to its framework skill.
- Avoid package or class renames without tracing configuration strings, service descriptors, serialized names, and downstream consumers.

## Release evidence

- Build the actual artifact type, not only compiled classes.
- For a library, inspect the published dependency metadata and public API/ABI report when configured.
- Exercise the oldest and newest supported runtime in the matrix when the change uses or alters an API, feature, dependency, or build setting whose availability differs across runtimes.
- Report intentional JDK, bytecode, dependency, module, generated, or packaging changes.

For `javac` and JPMS details, select the tool and specification editions matching the repository's effective target JDK. Primary references: [Maven Wrapper](https://maven.apache.org/wrapper/), [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html), [Java SE documentation index](https://docs.oracle.com/en/java/javase/), and [Java Language Specification index](https://docs.oracle.com/javase/specs/jls/).
