# Rust Migration Protocol

WHEN converting an existing tool from another language to Rust THEN you SHALL follow this protocol.
You SHALL extend the Standard workflow with the additions below at each phase.

---

## Table of contents

1. [Phase 0 additions — Behavior capture](#phase-0-additions)
2. [Phase 1 additions — Implementation constraints](#phase-1-additions)
3. [Phase 2 additions — Behavior comparison](#phase-2-additions)
4. [Workspace layout](#workspace-layout)
5. [Invocation wrappers](#invocation-wrappers)
6. [Incremental migration](#incremental-migration)

---

## Phase 0 additions

You SHALL complete behavior capture before writing Rust stubs.

### Behavior capture table

You SHALL document every aspect of the original tool:

| Aspect | You SHALL document |
|---|---|
| Name and original path | e.g., `scripts/foo.py` |
| Language | e.g., Python 3.11 |
| Purpose | One-sentence description |
| CLI interface | All arguments, flags, and options in a table |
| Exit codes | All exit codes and their meanings in a table |
| stdout behavior | What is written to stdout and its format |
| stderr behavior | What is written to stderr and its format |
| File inputs | What files it reads and their expected formats |
| File outputs | What files it writes and their expected formats |
| Environment variables | What env vars it reads, with defaults |
| External dependencies | External commands or services it calls |

### Test case extraction

You SHALL list three or more example invocations with expected stdout, stderr, and exit code.
You SHALL include at least one error case with expected exit code and stderr.
You SHALL document any edge cases discovered.
You SHALL capture original outputs as golden files:

```bash
mkdir -p tests/fixtures
<original-tool> <args> > tests/fixtures/case1.stdout 2> tests/fixtures/case1.stderr
echo $? > tests/fixtures/case1.exit
```

### Migration plan

You SHALL identify the Rust workspace root.
You SHALL propose: crate name, binary name, module structure.
You SHALL list expected dependencies with justification for each.
You SHALL propose a wrapper script or symlink for invocation compatibility.

### Mapping table

You SHALL produce a mapping table:

| Original path | Rust binary | Crate path | Wrapper invocation |
|---|---|---|---|
| `scripts/foo.py` | `foo` | `tools/rust/cli/src/bin/foo.rs` | `scripts/foo.py` (shim; forwards to `foo`) |

---

## Phase 1 additions

### Behavior preservation

You SHALL preserve the following exactly:

| Aspect | Requirement |
|---|---|
| CLI arguments | Identical flags, options, and positional arguments |
| Exit codes | Identical exit codes for identical conditions |
| stdout format | Identical output format including whitespace and ordering |
| stderr format | Identical error message format |
| File outputs | Identical file contents and locations |
| Environment variables | Same env vars read with same defaults |

WHEN the original tool has ambiguous or inconsistent behavior THEN you SHALL match the original for compatibility.
WHEN matching ambiguous behavior THEN you SHALL document the inconsistency.
WHEN documenting an inconsistency THEN you SHALL propose a follow-up improvement as a separate task.

### Wrapper creation

WHEN the original tool was invoked via an interpreter THEN you SHALL keep a shim at the exact same path that execs the Rust binary and forwards args and exit code.
You SHALL ensure users can invoke the tool with the same path pattern.

### Async decision

WHEN the original tool was synchronous THEN the Rust version SHALL be synchronous unless concurrency provides measurable benefit.

---

## Phase 2 additions

### Behavior comparison

You SHALL run both original and Rust tool with identical inputs and diff outputs:

```bash
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

<original-tool> <args> > "$tmp_dir/original.out" 2> "$tmp_dir/original.err"
echo $? > "$tmp_dir/original.exit"

<rust-tool> <args> > "$tmp_dir/rust.out" 2> "$tmp_dir/rust.err"
echo $? > "$tmp_dir/rust.exit"

diff "$tmp_dir/original.out" "$tmp_dir/rust.out"
diff "$tmp_dir/original.err" "$tmp_dir/rust.err"
diff "$tmp_dir/original.exit" "$tmp_dir/rust.exit"
```

You SHALL confirm all diffs are empty.

---

## Workspace layout

You SHALL place all Rust crates under one Rust root.
You SHALL maintain one `Cargo.lock` and one `target/`.
You SHALL make each converted tool a separate executable — you SHALL NOT force a mega-CLI.
You SHALL NOT create `Cargo.toml` outside the Rust root.
You SHALL use stable Rust.
You SHALL NOT introduce new telemetry.
You SHALL NOT introduce new network calls beyond what the original tool performed.

---

## Invocation wrappers

You SHALL keep old tool invocation working during transition.

Python shim template:

```python
#!/usr/bin/env python3
"""Shim that forwards to the Rust binary."""
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.abspath(os.path.join(script_dir, ".."))
configured_bin = os.environ.get("TOOL_NAME_BIN")
target_dir = os.environ.get("CARGO_TARGET_DIR", os.path.join(workspace_root, "target"))

candidates = []
if configured_bin:
    candidates.append(configured_bin)
candidates.extend(
    [
        os.path.join(target_dir, "release", "tool-name"),
        os.path.join(target_dir, "debug", "tool-name"),
    ]
)

for rust_bin in candidates:
    if os.path.isfile(rust_bin) and os.access(rust_bin, os.X_OK):
        os.execv(rust_bin, [rust_bin] + sys.argv[1:])

sys.stderr.write(
    "error: tool-name binary not found; build it or set TOOL_NAME_BIN\n"
)
sys.exit(127)
```

---

## Incremental migration

You SHALL convert one tool at a time.
You SHALL keep the workspace building and testing after each tool.
You SHALL NOT perform big-bang migrations unless explicitly requested.
