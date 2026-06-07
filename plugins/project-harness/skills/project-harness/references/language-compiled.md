# Go, C/C++, .NET, and Zig Commands

Use this file for compiled ecosystems other than Rust.

## Go

Default command family:

```text
build      go build ./...
test       go test ./...
lint       golangci-lint run
fmt        gofmt -w .
fmt-check  test -z "$(gofmt -l .)"
clean      go clean -cache
bootstrap  go mod download
```

Binary hints:
- `cmd/<name>/`
- root `main.go`

For staged binaries, build explicit `main` packages instead of assuming every
package produces an executable.

## C / C++ with CMake

Default command family:

```text
build      cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build
test       cd build && ctest --output-on-failure
clean      rm -rf build
bootstrap  cmake -S . -B build
```

Do not force clang-tidy or clang-format if the repo does not already use them.

## .NET

Default command family:

```text
build      dotnet build
test       dotnet test
lint       dotnet format --verify-no-changes
fmt        dotnet format
clean      dotnet clean
bootstrap  dotnet restore
```

For staged outputs, prefer `dotnet publish -c Release -o <outdir>`.

## Zig

Default command family:

```text
build      zig build
test       zig build test
fmt        zig fmt src/
fmt-check  zig fmt --check src/
clean      rm -rf zig-out zig-cache .zig-cache
bootstrap  zig build
```

## Dist guidance

These ecosystems vary more than Rust. Only auto-generate staging logic when the
output path is obvious.

Safe cases:
- Go `cmd/` binaries
- `.NET` `dotnet publish`
- CMake projects with clear executable targets and known output paths

Unsafe cases:
- mixed library and binary workspaces
- custom post-build packaging
- generated SDK or installer pipelines

In unsafe cases, keep the justfile in `general` mode and write dist workflow
candidates for manual customization.
