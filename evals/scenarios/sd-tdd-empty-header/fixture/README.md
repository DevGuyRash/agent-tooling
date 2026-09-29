# mirrorsync

Keeps local package mirrors in sync with their upstreams. This repository holds the configuration reader and the `check` command; the sync engine lives in its own repository and imports `mirrorsync.config`.

```sh
python3 -m mirrorsync check /etc/mirrorsync/mirrors.ini
```

`check` parses the file, fills each mirror from `[defaults]`, and prints one line per mirror, or the problems it found (exit status 1). See `mirrors.example.ini`.

## Configuration format

An INI dialect, read by `mirrorsync.config.parse` (text) and `mirrorsync.config.load` (a path, UTF-8 with or without a BOM). The result is `{section: {key: value}}` in file order.

- A section starts with a header line, `[name]`. Whitespace around the name inside the brackets is ignored (`[ debian ]` is the section `debian`); whitespace within the name is kept (`[debian ports]`). A header must name a section. Section names are case-sensitive, and each section may appear once.
- Every other line is `key = value` or `key: value`, split at the first `=` or `:`. Keys are case-insensitive (stored in lower case) and may appear once per section. Whitespace around keys and values is removed, and a value may be empty.
- A line that starts with a space or a tab continues the value of the key above it while that value is open; its text is appended after a newline. A blank line closes the value. Outside a value, leading whitespace is ignored.
- Lines whose first non-blank character is `#` or `;` are comments, including inside a multi-line value. There are no end-of-line comments: a `#` after a value is part of the value.
- Anything else raises `mirrorsync.config.ConfigError`, whose `lineno` is the offending line.

## Development

Python 3.10 or newer, standard library only. Run the tests from the repository root:

```sh
python3 -m unittest
```
