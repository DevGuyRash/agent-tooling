# Reporter Tools

Four optional scripts expose bounded structural observations. You MAY run a reporter when its observation helps the live decision. Their exit status is not an audit verdict. Source inspection remains useful when a reporter's assumptions could hide a defect or create a false one.

You MAY invoke a script by its installed path, for example `sh <skills-file-root>/scripts/reference_check.sh /absolute/path/to/target-skill --format json`. You SHOULD use each script's `--help` for its accepted arguments. Paths passed as targets resolve from the caller's current directory; an absolute target avoids that ambiguity. The `plugin_check.sh` target is a plugin directory; the other three take a skill directory. They can inspect targets outside this package and do not load the target's instructions as their own authority.

| Script | Observation and limits |
| --- | --- |
| `frontmatter_check.sh` | Extracts required metadata and reports naming and description bytes. Its lightweight YAML reader does not establish parsed-character limits or replace a complete host parser. |
| `reference_check.sh` | Resolves supported literal Markdown resource paths from the declaring document, preserving sibling prefixes. Reports missing files separately from unlinked, nested, or ambiguous references. It does not check remote URLs, anchors, dynamic paths, or semantic adequacy. |
| `script_sanity.sh` | Reports script line endings, shebangs, executable bits, and cold-start clues. It does not run the target or establish permission, safety, or correct effects. |
| `plugin_check.sh` | Parses manifest and catalog JSON, compares decoded values, and records file content, executable bits, topology, and symlink destinations without following directory links. Its bounded skill-description reader leaves unsupported YAML forms unchecked. It does not establish native host acceptance, the active cache from multiple candidates, or end-to-end usefulness. |

The scripts need a POSIX shell, ordinary Unix text tools, and Python 3's standard library. They install nothing. JSON output is compact and preserves control characters and Unicode values; text output separates errors from observations. For frontmatter, references, and script sanity, exit 0 means no reported structural errors and 1 means structural errors. The plugin reporter emits observations and returns 0 when collection succeeds. Exit 2 means unusable arguments, input, or failed collection. Malformed JSON sources and ambiguous duplicate keys cannot supply a successful plugin report. Any malformed report or unexpected nonzero exit is a tool failure, never a clean target.

For a tool failure, you SHOULD inspect the actual error and correct the invocation or dependency before retrying; unchanged-input retries do not add evidence. Reports do not modify the target. The reference checker labels examples and ambiguous expressions as unverified instead of shortening them into apparently broken literal paths. You SHOULD resolve those manually when material. Repository target selection, CI orchestration, and release requirements live in repository tooling, separate from these reusable reporters.
