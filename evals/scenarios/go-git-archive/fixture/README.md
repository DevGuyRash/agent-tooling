# shipkit

The release helper for the Tidewater projects (tidewatch, harbor-bell, and friends). Run it from the top of a project's repository; it reads the project's name from `.shipkit` and works from its git history and tags.

```sh
go build ./cmd/shipkit      # leaves ./shipkit
cd ~/src/tidewatch && ~/src/shipkit/shipkit next minor
```

## Commands

- `shipkit next major|minor|patch`: the version after the newest release (`docs/next.md`, which also says what counts as a release tag).
- `shipkit notes`: the commits since the newest release, for the release notes (`docs/notes.md`).

## .shipkit

```
# the project's name, as in its tarballs and the Homebrew formula
name = tidewatch
```

## Working on it

Standard library only (the release machine builds offline). shipkit runs git for everything it knows about a repository, through `internal/gitx`. Tests need git on PATH:

```sh
go test ./...
```
