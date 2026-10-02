# shipkit next

    shipkit next major|minor|patch

Prints the version after the newest release, with that part bumped: `1.10.2` gives `2.0.0`, `1.11.0`, or `1.10.3`. With no release yet it prints `0.1.0`.

## Release tags

A release tag is `v` and then MAJOR.MINOR.PATCH, each a decimal number with no leading zero: `v1.10.2`. Tags with a pre-release part (`v2.0.0-rc.1`) and any other tags (`nightly`) are not releases. Releases are ordered by their numbers, so `v1.10.0` is newer than `v1.9.0`. `internal/semver` implements this.
