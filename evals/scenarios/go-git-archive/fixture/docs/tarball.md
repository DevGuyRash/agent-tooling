# shipkit tarball

    shipkit tarball [-o DIR] [VERSION]

Makes the source tarball for a release and records its checksum. Agreed in the release meeting on 18 September; not written yet.

- VERSION is MAJOR.MINOR.PATCH, with or without a leading `v`; the release's tag is `vMAJOR.MINOR.PATCH`. Without VERSION, the newest release tag (`docs/next.md`).
- The tarball is `DIR/NAME-MAJOR.MINOR.PATCH.tar.gz`, where NAME comes from `.shipkit` and DIR defaults to `dist`. DIR is created when it does not exist, and a tarball already there under that name is replaced.
- Its bytes are exactly what

      git archive --format=tar.gz --prefix=NAME-MAJOR.MINOR.PATCH/ vMAJOR.MINOR.PATCH

  writes. That is the tarball GitHub serves for the tag, and the Homebrew formula pins its sha256, so anything else breaks `brew install`. It honors the project's `.gitattributes` (`export-ignore`, `export-subst`) the way GitHub's does.
- `DIR/SHA256SUMS` has one line per tarball, `HEX  FILE`: the sha256 in lowercase hex, two spaces, and the file name without DIR, the format `sha256sum` writes and `sha256sum -c` reads. The new tarball's line is added, or replaces the line already there for that file name; the other lines stay as they are; the lines are sorted by file name. The file is created when it does not exist.
- Standard output is the line written to SHA256SUMS.

## Errors

On standard error as `shipkit: MESSAGE`, with exit status 1, and nothing written:

- no `.shipkit`, or not a git repository, as the other commands report them
- `bad version 1.2`: VERSION is not MAJOR.MINOR.PATCH (a pre-release such as `2.0.0-rc.1` is not a release either)
- `no tag v1.3.0`: the release's tag does not exist
- `no release tags`: VERSION was left out and there is no release tag
