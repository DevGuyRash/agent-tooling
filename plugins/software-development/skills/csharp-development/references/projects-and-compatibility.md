# C# Projects and Compatibility

## Resolve the effective SDK and build

- Read `global.json`, project SDKs, target frameworks, imports, `Directory.Build.props/targets`, workload manifests, and CI together.
- `global.json` controls SDK selection policy; it does not by itself change a project's target framework or runtime behavior.
- Prefer repository scripts and `dotnet`/MSBuild commands with their encoded properties over ad hoc IDE-only builds.
- Preserve conditional properties, configurations, platforms, runtime identifiers, and custom targets.
- Do not manually edit generated project artifacts, source-generator output, assets files, or intermediate directories.

## Keep language, framework, and runtime aligned

- Distinguish SDK version, C# language version, target framework, reference assemblies, runtime, and deployment model.
- Avoid `LangVersion=latest` or target-framework upgrades unless the task requires moving the compatibility floor.
- When multi-targeting, keep conditional code and package references valid for every target.
- Treat trimming, single-file, ReadyToRun, Native AOT, COM, native libraries, and platform analyzers as separate compatibility surfaces when enabled.
- Route ASP.NET, Entity Framework, Blazor, MAUI, Unity, and other framework build semantics to their framework skills.

## Change NuGet dependencies narrowly

- Respect central package management, package source mapping, signature/integrity policy, lock files, and repository restore settings.
- Add or update only packages required by the task. Inspect direct, transitive, target-specific, central, and lock changes.
- Preserve `PrivateAssets`, `IncludeAssets`, development-only, analyzer, source-generator, and runtime asset intent.
- Check package compatibility across all target frameworks and runtime identifiers before accepting a resolution.
- Do not persist credentials, machine feeds, cache paths, or local package sources in repository files.

## Generated and public surfaces

- Edit the schema, template, or annotated source that owns generated code and regenerate through the repository command.
- Treat source generators and analyzers as build inputs whose versions affect output and diagnostics.
- Preserve assembly names, namespaces, strong names, internals visibility, type forwarding, resource names, and reflection-visible attributes.
- For public packages, inspect API baselines, XML docs, symbols, source packages, dependency metadata, and deterministic-build settings.
- Check configuration binding and serializer source-generation contracts when those files or attributes change, while routing framework behavior outward.
- For native interop, match exact widths, encodings, calling conventions, ownership, and allocation/free pairs; prefer `SafeHandle` for owned handles where suitable and root callbacks for the complete native registration lifetime. Select `LibraryImport`, `DllImport`, or another binding mechanism from the target/runtime contract, then verify representative native consumers and configured trimming/AOT deployments.

## Avoid environment drift

- Do not install workloads, SDKs, global tools, templates, or certificates unless the task requires them.
- Do not bypass NuGet verification or repository feeds merely to make restore pass.
- Distinguish missing SDK/workload/feed state from source failure and report it accurately.
- Keep local caches, user secrets, and machine-specific paths out of committed project configuration.

## Release evidence

- Build the actual deployable or package output, not only one project's default target.
- Verify every affected target framework/configuration available in the repository matrix.
- Run API compatibility and package validation when public surface or packaging changes.
- Report intentional SDK, language, framework, package, generated, trimming/AOT, or publication changes.

Primary references: [`global.json`](https://learn.microsoft.com/dotnet/core/tools/global-json), [target frameworks](https://learn.microsoft.com/dotnet/standard/frameworks), [central package management](https://learn.microsoft.com/nuget/consume-packages/central-package-management), [lock files](https://learn.microsoft.com/nuget/consume-packages/package-references-in-project-files#locking-dependencies), [native interop](https://learn.microsoft.com/dotnet/standard/native-interop/best-practices).
