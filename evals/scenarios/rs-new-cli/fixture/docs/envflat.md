# envflat

Our services read their settings from environment files (`/etc/<service>/env`, which the unit's start script loads with `set -a; . /etc/<service>/env`), but we keep the settings themselves as JSON in the deploy repo. `envflat` turns one JSON settings file into an environment file.

```
envflat [--prefix NAME] [FILE]
```

It reads one JSON document from FILE, or from standard input when FILE is omitted or is `-`, and writes one `KEY=VALUE` line per value to standard output.

## Keys

- The document must be an object.
- Every string, number, `true`, `false`, and `null` in it becomes one line, in the order it appears in the file. Objects and arrays only contribute to keys; an empty object or array produces no lines.
- A value's KEY is its path from the top of the document, one component per level, joined with `__` (two underscores). An object member's component is its name upper-cased, with every character that is not an ASCII letter or digit replaced by `_` (one `_` per character). An array element's component is its index, counting from 0.
- With `--prefix NAME`, NAME, transformed the same way, is the first component.
- Two values that end up with the same KEY are an error (`duplicate key KEY`).

## Values

- Strings are written with their JSON escapes decoded (`\"`, `\u00e9`, surrogate pairs, and so on).
- Numbers are written exactly as they appear in the file: `1.50` stays `1.50` and `1e3` stays `1e3`.
- `true` and `false` are written as they are; `null` is written as an empty value (`KEY=`).
- A string is written bare when it is non-empty and has only ASCII letters, digits, and the characters `_ - . / : @ + , %`. Any other string, including the empty string, is wrapped in single quotes, with each `'` inside written as `'\''`.
- A string containing a control character (U+0000 to U+001F, or U+007F) is an error (`KEY: control character in value`): it cannot go in an env file.

## Errors

On any error envflat writes nothing to standard output, prints one line starting with `envflat: ` to standard error, and exits with status 1. That covers a file that cannot be read, input that is not valid JSON (RFC 8259, so no comments, trailing commas, `NaN`, or text after the document), a document that is not an object, a duplicate key, and a control character in a value. Usage errors (an unknown option, `--prefix` without a NAME, more than one FILE) exit with status 2.

## Example

`settings.json`:

```json
{
  "service": "billing-api",
  "http": {"port": 8080, "read-timeout": "2.5s", "tls": null},
  "db": {"host": "db-1.internal", "pool.max": 20, "password": "s3cr3t's"},
  "features": ["audit", "v2 invoices"],
  "ratio": 1.50,
  "debug": false
}
```

`envflat --prefix billing settings.json` prints:

```
BILLING__SERVICE=billing-api
BILLING__HTTP__PORT=8080
BILLING__HTTP__READ_TIMEOUT=2.5s
BILLING__HTTP__TLS=
BILLING__DB__HOST=db-1.internal
BILLING__DB__POOL_MAX=20
BILLING__DB__PASSWORD='s3cr3t'\''s'
BILLING__FEATURES__0=audit
BILLING__FEATURES__1='v2 invoices'
BILLING__RATIO=1.50
BILLING__DEBUG=false
```
