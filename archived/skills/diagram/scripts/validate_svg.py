#!/usr/bin/env python3
"""Pre-flight validator for visuals produced by the diagram skill.

Usage: python3 validate_svg.py <file.svg|file.html>
Exit 0 = clean (warnings allowed), exit 1 = errors found.

Checks are heuristic (text widths are estimated, not measured) — treat
errors as must-fix, warnings as look-twice. Pair with render_preview.sh
for visual confirmation.
"""
import re
import sys
import xml.etree.ElementTree as ET

ERR, WARN = "ERROR", "warn"
issues = []


def report(level, msg):
    issues.append((level, msg))


def tag_of(el):
    return el.tag.split("}")[-1]


def f(el, attr, default=0.0):
    v = el.get(attr)
    if v is None:
        return default
    try:
        return float(re.sub(r"[a-z%]+$", "", v.strip()))
    except ValueError:
        return default


def text_content(el):
    parts = [el.text or ""]
    for ts in el:
        if tag_of(ts) == "tspan":
            parts.append(ts.text or "")
    return "".join(parts).strip()


def est_width(s, size14):
    if not s:
        return 0
    w = 0.0
    for ch in s:
        if ord(ch) > 0x2E80:
            w += 15
        else:
            w += 8 if size14 else 7
    if re.search(r"[₀-₉⁰-⁹∑∫√≤≥±×÷]", s):
        w *= 1.2
    return w


def seg_hits_box(x1, y1, x2, y2, bx, by, bw, bh, inset=2, samples=24):
    """True if the segment passes through the box interior while neither
    endpoint sits on/near that box (within 8px of its edges)."""
    def near(px, py):
        return (bx - 8 <= px <= bx + bw + 8) and (by - 8 <= py <= by + bh + 8)

    if near(x1, y1) or near(x2, y2):
        return False
    for i in range(1, samples):
        t = i / samples
        px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        if (bx + inset < px < bx + bw - inset) and (by + inset < py < by + bh - inset):
            return True
    return False


def validate_svg(path):
    raw = open(path, encoding="utf-8").read()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        report(ERR, f"XML parse failure: {e}")
        return

    vb = root.get("viewBox", "")
    m = re.match(r"\s*([\d.+-]+)[ ,]+([\d.+-]+)[ ,]+([\d.+-]+)[ ,]+([\d.+-]+)", vb)
    if not m:
        report(ERR, "missing or malformed viewBox")
        return
    vx, vy, vw, vh = (float(g) for g in m.groups())
    if vx != 0 or vy != 0:
        report(ERR, f"viewBox must start at 0 0 (got {vx} {vy})")
    if abs(vw - 680) > 0.5:
        report(WARN, f"viewBox width {vw:g} ≠ 680 — label-width math assumes 680")

    if root.get("role") != "img":
        report(WARN, 'root <svg> missing role="img"')
    child_tags = [tag_of(c) for c in root]
    if "title" not in child_tags or "desc" not in child_tags:
        report(WARN, "missing <title>/<desc> accessibility children")

    rects, lines, texts = [], [], []
    max_bottom, max_right = 0.0, 0.0

    for el in root.iter():
        t = tag_of(el)
        if t == "rect":
            x, y, w, h = f(el, "x"), f(el, "y"), f(el, "width"), f(el, "height")
            rx = f(el, "rx")
            if (el.get("width") == "100%" or w >= vw * 0.95) and x <= 1 and y <= 1:
                pass  # background rect candidate; skip geometry checks
            else:
                rects.append((x, y, w, h, el))
                max_bottom = max(max_bottom, y + h)
                max_right = max(max_right, x + w)
                if x < 0 or y < 0:
                    report(ERR, f"rect at ({x:g},{y:g}) has negative coordinates")
                if x + w > vw + 0.5:
                    report(ERR, f"rect right edge {x + w:g} exceeds viewBox width {vw:g}")
                if rx > h / 2 and h > 0:
                    report(WARN, f"rect at ({x:g},{y:g}): rx {rx:g} ≥ height/2 — renders as a pill")
        elif t == "line":
            x1, y1, x2, y2 = f(el, "x1"), f(el, "y1"), f(el, "x2"), f(el, "y2")
            lines.append((x1, y1, x2, y2, el))
            max_bottom = max(max_bottom, y1, y2)
            max_right = max(max_right, x1, x2)
            if min(x1, y1, x2, y2) < 0:
                report(ERR, f"line ({x1:g},{y1:g})→({x2:g},{y2:g}) has negative coordinates")
        elif t == "text":
            x, y = f(el, "x"), f(el, "y")
            content = text_content(el)
            cls = el.get("class", "")
            fs = f(el, "font-size", 0)
            size14 = ("th" in cls.split() or cls.split() == ["t"] or fs >= 13)
            w = est_width(content, size14)
            anchor = el.get("text-anchor", "start")
            if anchor == "middle":
                x0, x1_ = x - w / 2, x + w / 2
            elif anchor == "end":
                x0, x1_ = x - w, x
            else:
                x0, x1_ = x, x + w
            texts.append((x0, y - 10, x1_ - x0, 14, content, el))
            max_bottom = max(max_bottom, y + 4)
            max_right = max(max_right, x1_)
            if not cls and not el.get("fill") and "fill" not in el.get("style", ""):
                report(WARN, f'text "{content[:30]}" has no class and no fill — invisible-in-dark-mode risk')
            if 0 < fs < 11:
                report(ERR, f'text "{content[:30]}" font-size {fs:g} < 11px minimum')
            if x0 < -0.5:
                report(ERR, f'text "{content[:30]}" extends to x={x0:.0f} — past the left edge (anchor/width problem)')
            if x1_ > vw + 0.5:
                report(ERR, f'text "{content[:30]}" extends to x={x1_:.0f} — past viewBox width {vw:g}')
        elif t in ("path", "polyline"):
            has_fill = el.get("fill") is not None or "fill" in el.get("style", "")
            connector = el.get("marker-end") or (el.get("stroke") and t == "polyline")
            if not has_fill and (connector or el.get("stroke")):
                report(ERR, f"<{t}> with stroke/marker has no fill attribute — add fill=\"none\" or it renders as a black blob")
            nums = re.findall(r"-?\d+\.?\d*", el.get("d", "") or el.get("points", ""))
            if any(float(n) < -0.5 for n in nums):
                report(WARN, f"<{t}> contains negative coordinates — verify it stays inside the viewBox")

    # viewBox height vs content
    if max_bottom > vh + 0.5:
        report(ERR, f"content bottom {max_bottom:.0f} exceeds viewBox height {vh:g} — clipped")
    elif vh - max_bottom > 100:
        report(WARN, f"{vh - max_bottom:.0f}px of empty space below content — set height ≈ {max_bottom + 40:.0f}")
    elif vh - max_bottom < 10:
        report(WARN, "less than 10px breathing room below content")

    # text fits its enclosing box
    for tx0, ty0, tw, th_, content, tel in texts:
        cx, cy = tx0 + tw / 2, ty0 + th_ / 2
        enclosing = [r for r in rects if r[0] <= cx <= r[0] + r[2] and r[1] <= cy <= r[1] + r[3]]
        if enclosing:
            box = min(enclosing, key=lambda r: r[2] * r[3])
            if tw + 24 > box[2] + 0.5:
                report(ERR, f'"{content[:34]}" est. {tw:.0f}px + 24px padding > its {box[2]:g}px box — shorten label or widen box')

    # unrelated text-text collisions
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            if (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                    and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]):
                report(ERR, f'text collision: "{a[4][:24]}" overlaps "{b[4][:24]}"')

    # lines slashing through boxes or text
    for x1, y1, x2, y2, lel in lines:
        if "leader" in lel.get("class", ""):
            continue
        for bx, by, bw, bh, rel in rects:
            if seg_hits_box(x1, y1, x2, y2, bx, by, bw, bh):
                report(WARN, f"line ({x1:g},{y1:g})→({x2:g},{y2:g}) passes through a box at ({bx:g},{by:g}) — reroute with an L-bend")
        for tx0, ty0, tw, th_, content, tel in texts:
            if seg_hits_box(x1, y1, x2, y2, tx0, ty0, tw, th_):
                report(WARN, f'line crosses text "{content[:28]}" — move the label or the line')

    # same-row rect spacing
    rows = {}
    for x, y, w, h, el in rects:
        rows.setdefault(round(y / 8), []).append((x, w))
    for row in rows.values():
        row.sort()
        for (x1_, w1), (x2_, _) in zip(row, row[1:]):
            gap = x2_ - (x1_ + w1)
            if gap < -0.5:
                report(ERR, f"boxes overlap in a row near x={x1_:g} (gap {gap:.0f}px) — recompute tier packing")
            elif gap < 18:
                report(WARN, f"boxes only {gap:.0f}px apart near x={x1_:g} — minimum comfortable gap is 20px")

    # background presence
    first_rects = [c for c in root.iter() if tag_of(c) == "rect"]
    has_bg = any(
        (r.get("width") == "100%" or f(r, "width") >= vw * 0.95)
        and f(r, "x") <= 1 and f(r, "y") <= 1
        for r in first_rects[:3]
    )
    if not has_bg:
        report(WARN, "no full-canvas background rect found — standalone files render on unknown backdrops")

    if "prefers-color-scheme" not in raw and "c-" in raw:
        report(WARN, "ramp classes used but no dark-mode @media block found — embed the tokens stylesheet")


def validate_html(path):
    raw = open(path, encoding="utf-8").read()
    if "<!DOCTYPE" not in raw[:200]:
        report(ERR, "standalone HTML needs <!DOCTYPE html>")
    for m in re.finditer(r"<canvas\b[^>]*>", raw):
        tag = m.group(0)
        if 'role="img"' not in tag:
            report(ERR, "canvas missing role=\"img\" + aria-label")
        if re.search(r'style="[^"]*height', tag):
            report(ERR, "height set on <canvas> itself — set it on the wrapper div only")
    if "prefers-color-scheme" not in raw:
        report(WARN, "no dark-mode media query — page will glare in dark mode")
    if "<script" in raw:
        last_script = raw.rfind("<script")
        if "</body>" in raw and last_script > raw.rfind("</body>"):
            report(WARN, "script appears after </body>")
    if re.search(r"position:\s*fixed", raw):
        report(WARN, "position:fixed found — fine in standalone pages, but use the faux-viewport pattern for modal mockups")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    path = sys.argv[1]
    if path.endswith(".svg"):
        validate_svg(path)
    elif path.endswith(".html") or path.endswith(".htm"):
        validate_html(path)
    else:
        print("expected an .svg or .html file")
        sys.exit(2)

    errors = [m for lvl, m in issues if lvl == ERR]
    warns = [m for lvl, m in issues if lvl == WARN]
    for lvl, msg in issues:
        print(f"[{lvl}] {msg}")
    print(f"\n{path}: {len(errors)} error(s), {len(warns)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
