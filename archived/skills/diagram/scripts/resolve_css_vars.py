#!/usr/bin/env python3
"""Resolve CSS custom properties in a standalone SVG to literal values.

Non-browser rasterizers (librsvg, ImageMagick's SVG path, often inkscape)
don't implement CSS custom properties: an unresolved var() invalidates the
declaration and the fill computes to black. Browsers resolve them fine, so
delivered files are correct — but previews lie. This pre-resolver
substitutes the light-mode values (custom-property definitions found
OUTSIDE any @media block) so rasterized previews match what a light-mode
browser shows. See eval/failures/002-rsvg-css-variables.

Usage: resolve_css_vars.py <in.svg> <out.svg>

Limitations (fine for token-system files): fallbacks containing parentheses
inside var(--x, fallback) are not parsed; definitions are taken file-wide,
not per-selector.
"""
import re
import sys


def strip_media_blocks(text):
    """Remove @media { ... } blocks (balanced braces) so only the
    light-mode custom-property definitions remain."""
    out, i, n = [], 0, len(text)
    while i < n:
        m = text.find("@media", i)
        if m == -1:
            out.append(text[i:])
            break
        out.append(text[i:m])
        j = text.find("{", m)
        if j == -1:
            break
        depth, j = 1, j + 1
        while j < n and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    src, dst = sys.argv[1], sys.argv[2]
    raw = open(src, encoding="utf-8").read()

    light = strip_media_blocks(raw)
    defs = dict(re.findall(r"--([\w-]+)\s*:\s*([^;{}]+)", light))

    pat = re.compile(r"var\(\s*--([\w-]+)\s*(?:,\s*([^()]*?))?\s*\)")

    def sub(m):
        name, fallback = m.group(1), m.group(2)
        v = defs.get(name)
        if v is None:
            v = fallback if fallback is not None else m.group(0)
        return v.strip()

    out = raw
    for _ in range(4):  # handle var-in-var definitions
        new = pat.sub(sub, out)
        if new == out:
            break
        out = new

    open(dst, "w", encoding="utf-8").write(out)


if __name__ == "__main__":
    main()
