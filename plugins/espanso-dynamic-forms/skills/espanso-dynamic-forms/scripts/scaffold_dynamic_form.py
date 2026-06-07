#!/usr/bin/env python3
"""Generate portable scaffolds for dynamic Espanso form providers."""

from __future__ import annotations

import argparse
import re
import sys

RUST_IDENTIFIER_RE = re.compile(r"[a-z_][a-z0-9_]*")
RUST_RESERVED_WORDS = {
    "abstract",
    "as",
    "async",
    "await",
    "become",
    "box",
    "break",
    "const",
    "continue",
    "crate",
    "do",
    "dyn",
    "else",
    "enum",
    "extern",
    "false",
    "final",
    "fn",
    "for",
    "if",
    "impl",
    "in",
    "let",
    "loop",
    "macro",
    "match",
    "mod",
    "move",
    "mut",
    "override",
    "priv",
    "pub",
    "ref",
    "return",
    "self",
    "static",
    "struct",
    "super",
    "trait",
    "true",
    "try",
    "type",
    "typeof",
    "union",
    "unsafe",
    "unsized",
    "use",
    "virtual",
    "where",
    "while",
    "yield",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate dynamic form scaffolds (YAML + provider dispatch skeleton)."
    )
    parser.add_argument("--provider", required=True, help="Provider id")
    parser.add_argument("--fields", default="", help="Comma-separated field names")
    parser.add_argument("--operation", default="layout", help="Operation name")
    parser.add_argument(
        "--format",
        choices=("all", "yaml", "provider"),
        default="all",
        help="Output selection",
    )
    return parser.parse_args()


def normalize_fields(raw: str, *, rust_identifiers: bool) -> list[str]:
    fields: list[str] = []
    for part in raw.split(","):
        name = part.strip().lower()
        if not name:
            continue
        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError(
                f"invalid field name '{part.strip()}': use lowercase letters, digits, and underscore only (e.g. input_mode)"
            )
        if rust_identifiers and (
            not RUST_IDENTIFIER_RE.fullmatch(name) or name in RUST_RESERVED_WORDS
        ):
            raise ValueError(
                f"invalid field name '{part.strip()}': provider scaffold requires a Rust-safe identifier "
                "(start with lowercase letter/underscore, then lowercase letters/digits/underscore, and avoid Rust keywords)"
            )
        fields.append(name)
    return fields


def yaml_scaffold(operation: str, provider: str, fields: list[str]) -> str:
    lines = [
        "# layout_generator args",
        '  - "%CONFIG%/tools/rust/bin/espanso_env"',
        f"  - ESPANSO_FORM_OPERATION={operation}",
        f"  - ESPANSO_FORM_PROVIDER={provider}",
    ]
    for field in fields:
        lines.append(f"  - ESPANSO_FORM_FIELD_{field}={{{{form1.{field}}}}}")
    lines.append('  - "%CONFIG%/tools/rust/bin/<layout-generator>"')
    return "\n".join(lines)


def provider_scaffold(provider: str, fields: list[str]) -> str:
    field_reads = "\n".join(
        f'    let {field} = request.field("{field}").unwrap_or("");'
        for field in fields
    )
    return f"""# Provider-dispatch pseudocode
match request.provider.as_str() {{
    "{provider}" => {{
{field_reads}
        let layout = "Input:\\n[[input]]\\n\\nOutput Mode:\\n[[output_mode]]";
        emit_layout(layout)
    }}
    _ => {{
        eprintln!("unsupported provider: {{}}", request.provider);
        2
    }}
}}"""


def main() -> int:
    args = parse_args()
    requires_rust_identifiers = args.format in ("all", "provider")
    try:
        fields = normalize_fields(
            args.fields, rust_identifiers=requires_rust_identifiers
        )
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    if args.format in ("all", "yaml"):
        print("=== YAML scaffold ===")
        print(yaml_scaffold(args.operation, args.provider, fields))
        print()

    if args.format in ("all", "provider"):
        print("=== Provider scaffold ===")
        print(provider_scaffold(args.provider, fields))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
