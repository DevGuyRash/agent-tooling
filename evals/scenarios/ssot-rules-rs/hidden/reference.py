"""Reference for ssot-rules-rs: what `results FILE` prints (as the fixture computes it), what
`startline pursuit [--minutes N] FILE` prints (as docs/pursuit.md specifies it), and the race-file rules
both read, each under a Portsmouth Number list passed in, so the check can compute what both commands
should print after it edits one number of the list.

PN is the fixture's list (crates/results/src/handicap.rs). Results and pursuit return (exit status,
stdout, [stderr fragments])."""

PN = {
    "Comet": 1210, "Enterprise": 1116, "Finn": 1049, "GP14": 1130, "ILCA 4": 1207, "ILCA 6": 1147,
    "ILCA 7": 1100, "Mirror": 1386, "Optimist": 1642, "RS Aero 7": 1063, "RS Feva XL": 1240, "RS200": 1047,
    "RS400": 942, "Solo": 1142, "Topper": 1364, "Wayfarer": 1102,
}


def with_pn(**changes):
    """PN with some classes' numbers replaced (class names with spaces passed as a dict via `classes`)."""
    pn = dict(PN)
    pn.update(changes.get("classes", {}))
    return pn


class Bad(Exception):
    def __init__(self, line, message):
        super().__init__(f"line {line}: {message}" if line else message)


def clock(text):
    if len(text) != 8 or text[2] != ":" or text[5] != ":" or not (text[:2] + text[3:5] + text[6:]).isdigit():
        return None
    h, m, s = int(text[:2]), int(text[3:5]), int(text[6:])
    return h * 3600 + m * 60 + s if h < 24 and m < 60 and s < 60 else None


def fmt_clock(t):
    return f"{t // 3600:02d}:{t // 60 % 60:02d}:{t % 60:02d}"


def fmt_duration(t):
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}"


def parse(text):
    """{"name", "start", "boats": [{"line", "sail", "helm", "class", "finish"}]}; finish is seconds, "DNF",
    "DNS", or None. Raises Bad."""
    name = start = None
    boats = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        keyword, rest = parts[0], (parts[1].strip() if len(parts) > 1 else "")
        if keyword == "race":
            if name is not None:
                raise Bad(n, "second race line")
            if not rest:
                raise Bad(n, "race needs a name")
            name = rest
        elif keyword == "start":
            if start is not None:
                raise Bad(n, "second start line")
            start = clock(rest)
            if start is None:
                raise Bad(n, f'bad start time "{rest}"')
        elif keyword == "boat":
            fields = [f.strip() for f in rest.split("|")]
            if not 3 <= len(fields) <= 4:
                raise Bad(n, "a boat line is: boat SAIL | HELM | CLASS [| FINISH]")
            sail, helm, cls = fields[:3]
            if not sail or len(sail) > 6 or not sail.isdigit() or not sail.isascii():
                raise Bad(n, f'bad sail number "{sail}"')
            if not helm:
                raise Bad(n, f"sail {sail} has no helm")
            if not cls:
                raise Bad(n, f"sail {sail} has no class")
            f = fields[3] if len(fields) == 4 else ""
            finish = None if f == "" else f if f in ("DNF", "DNS") else clock(f)
            if finish is None and f not in ("",):
                raise Bad(n, f'bad finish "{f}"')
            other = next((b for b in boats if b["sail"] == sail), None)
            if other:
                raise Bad(n, f"sail {sail} is already entered on line {other['line']}")
            boats.append({"line": n, "sail": sail, "helm": helm, "class": cls, "finish": finish})
        else:
            raise Bad(n, f'unknown line "{keyword}"')
    if name is None:
        raise Bad(0, "no race line")
    if start is None:
        raise Bad(0, "no start line")
    for b in boats:
        if isinstance(b["finish"], int) and b["finish"] <= start:
            raise Bad(b["line"], f"finish {fmt_clock(b['finish'])} is not after the start {fmt_clock(start)}")
    return {"name": name, "start": start, "boats": boats}


def layout(rows, right):
    widths = [max(len(r[c]) for r in rows if c < len(r)) for c in range(max(len(r) for r in rows))]
    out = []
    for r in rows:
        cells = [(cell.rjust(widths[c]) if right[c] else cell.ljust(widths[c])) for c, cell in enumerate(r)]
        out.append("  ".join(cells).rstrip() + "\n")
    return "".join(out)


def corrected(elapsed, pn):
    return (elapsed * 2000 + pn) // (2 * pn)


def _number(boat, pn):
    if boat["class"] not in pn:
        raise Bad(boat["line"], f'no Portsmouth Number for class "{boat["class"]}"')
    return pn[boat["class"]]


def results(text, pn=PN):
    try:
        race = parse(text)
        finished, retired, absent = [], [], []
        for b in race["boats"]:
            number = _number(b, pn)
            if b["finish"] is None:
                raise Bad(b["line"], f"sail {b['sail']} has no finish yet")
            if b["finish"] == "DNF":
                retired.append((b, number))
            elif b["finish"] == "DNS":
                absent.append((b, number))
            else:
                elapsed = b["finish"] - race["start"]
                finished.append((b, number, elapsed, corrected(elapsed, number)))
    except Bad as e:
        return 1, None, ["results: ", str(e).split(": ", 1)[-1]]
    finished.sort(key=lambda f: (f[3], int(f[0]["sail"])))
    rows = [["place", "sail", "helm", "class", "PN", "elapsed", "corrected"]]
    place = 0
    for i, (b, number, elapsed, corr) in enumerate(finished):
        if i == 0 or finished[i - 1][3] != corr:
            place = i + 1
        rows.append([str(place), b["sail"], b["helm"], b["class"], str(number), fmt_duration(elapsed), fmt_duration(corr)])
    for label, group in (("DNF", retired), ("DNS", absent)):
        for b, number in group:
            rows.append([label, b["sail"], b["helm"], b["class"], str(number), "", ""])
    return 0, f"{race['name']}, start {fmt_clock(race['start'])}\n" + layout(rows, [False, False, False, False, True, True, True]), []


def pursuit(text, minutes=60, pn=PN):
    """`startline pursuit --minutes N FILE` on a race file's text (minutes already validated)."""
    try:
        race = parse(text)
        if not race["boats"]:
            raise Bad(0, "no boats entered")
        classes = {}
        for b in race["boats"]:
            classes.setdefault(b["class"], [_number(b, pn), 0])[1] += 1
    except Bad as e:
        return 1, None, ["startline: ", str(e).split(": ", 1)[-1]]
    slowest_class, (slowest, _) = max(classes.items(), key=lambda kv: (kv[1][0], kv[0]))
    base = minutes * 60
    rows = []
    for cls, (number, boats) in classes.items():
        offset = (2 * base * (slowest - number) + slowest) // (2 * slowest)
        rows.append((race["start"] + offset, cls, number, boats))
    rows.sort(key=lambda r: (r[0], r[1].encode()))
    table = [["start", "class", "PN", "boats"]] + [[fmt_clock(t), c, str(n), str(k)] for t, c, n, k in rows]
    title = f"{race['name']}: {minutes} minutes for {slowest_class} (PN {slowest})\n"
    return 0, title + layout(table, [False, False, True, True]), []
