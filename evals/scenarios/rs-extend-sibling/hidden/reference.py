#!/usr/bin/env python3
"""Reference for `td standings`, following fixture/docs/standings.md, and for the tournament file rules in
fixture/docs/format.md (as the fixture's trn crate enforces them). hidden/make_cases.py runs it as

    python3 reference.py standings [--after-round N] [--tiebreaks LIST] FILE

to compute the expected exit status and standard output of every hidden case. Only `standings` is
implemented; td's other commands are the fixture's own.
"""
import sys
from fractions import Fraction

HALF = Fraction(1, 2)
RESULTS = {  # token -> (white's points, black's points, played over the board)
    "1-0": (Fraction(1), Fraction(0), True),
    "0-1": (Fraction(0), Fraction(1), True),
    "1/2": (HALF, HALF, True),
    "+-": (Fraction(1), Fraction(0), False),
    "-+": (Fraction(0), Fraction(1), False),
    "--": (Fraction(0), Fraction(0), False),
    "*": None,
}
BYES = {"full": Fraction(1), "half": HALF, "zero": Fraction(0)}
TIEBREAKS = {"bh1": "BH1", "bh": "BH", "sb": "SB", "wins": "Wins"}
DEFAULT_TIEBREAKS = ["bh1", "bh", "sb", "wins"]


class Usage(Exception):
    pass


class Failure(Exception):
    pass


def whole(token):
    return token.isascii() and token.isdigit()


def parse(text):
    """(event, planned, players {no: (rating, name)} in file order, rounds [[entry]]), or Failure naming the
    line, as trn::parse does."""
    event = planned = None
    players = {}
    rounds = []
    open_round = None  # (line, seen set)

    def fail(n, msg):
        raise Failure(f"line {n}: {msg}")

    def num(n, what, token):
        if not whole(token):
            fail(n, f'{what} must be a whole number, not "{token}"')
        return int(token)

    def pair_once(n, no):
        if no not in players:
            fail(n, f"unknown player {no}")
        if no in open_round[1]:
            fail(n, f"player {no} appears twice in round {len(rounds)}")
        open_round[1].add(no)

    def close():
        missing = [no for no in sorted(players) if no not in open_round[1]]
        if missing:
            fail(open_round[0], f"player {missing[0]} is missing from round {len(rounds)}")

    for i, raw in enumerate(text.split("\n")):
        n = i + 1
        line = raw.rstrip("\r").strip()
        if not line or line.startswith("#"):
            continue
        f = line.split()
        if f[0] == "event":
            if event is not None:
                fail(n, "event given twice")
            name = line[len("event"):].strip()
            if not name:
                fail(n, "event needs a name")
            event = name
        elif f[0] == "rounds":
            if planned is not None:
                fail(n, "rounds given twice")
            if len(f) != 2:
                fail(n, "usage: rounds N")
            planned = num(n, "the number of rounds", f[1])
            if planned == 0:
                fail(n, "a tournament needs at least one round")
        elif f[0] == "player":
            if rounds:
                fail(n, "players must come before round 1")
            if len(f) < 4:
                fail(n, "usage: player NO RATING NAME")
            no = num(n, "a start number", f[1])
            if no == 0:
                fail(n, "start numbers begin at 1")
            rating = num(n, "a rating", f[2])
            if rating != 0 and not 100 <= rating <= 3000:
                fail(n, f"rating {rating} is out of range")
            if no in players:
                fail(n, f"player {no} declared twice")
            players[no] = (rating, " ".join(f[3:]))
        elif f[0] == "round":
            if event is None or planned is None:
                fail(n, "event and rounds must come before round 1")
            if not players:
                fail(n, "no players before round 1")
            if len(f) != 2:
                fail(n, "usage: round N")
            given = num(n, "a round number", f[1])
            if open_round is not None:
                close()
            if given != len(rounds) + 1:
                fail(n, f"expected round {len(rounds) + 1}, found round {given}")
            if given > planned:
                fail(n, f"round {given} exceeds the {planned} planned rounds")
            rounds.append([])
            open_round = (n, set())
        elif f[0] == "bye":
            if open_round is None:
                fail(n, "bye before round 1")
            if len(f) != 3:
                fail(n, "usage: bye NO full|half|zero")
            no = num(n, "a start number", f[1])
            if f[2] not in BYES:
                fail(n, f'unknown bye "{f[2]}"')
            pair_once(n, no)
            rounds[-1].append(("bye", no, f[2]))
        elif whole(f[0]):
            if open_round is None:
                fail(n, "game before round 1")
            if len(f) != 3:
                fail(n, "usage: WHITE BLACK RESULT")
            white, black = num(n, "a start number", f[0]), num(n, "a start number", f[1])
            if f[2] not in RESULTS:
                fail(n, f'unknown result "{f[2]}"')
            if white == black:
                fail(n, f"player {white} cannot play itself")
            pair_once(n, white)
            pair_once(n, black)
            rounds[-1].append(("game", white, black, f[2]))
        else:
            fail(n, f'unknown statement "{f[0]}"')
    if open_round is not None:
        close()
    if event is None:
        raise Failure("missing event line")
    if planned is None:
        raise Failure("missing rounds line")
    if not players:
        raise Failure("no players")
    return event, planned, players, rounds


def finished(entries):
    return all(e[0] == "bye" or e[3] != "*" for e in entries)


def number(x):
    """The shortest decimal form of a multiple of 1/4: 0, 3, 3.5, 8.25."""
    whole_part, rest = divmod(x, 1)
    if rest == 0:
        return str(whole_part)
    return f"{whole_part}." + {Fraction(1, 4): "25", Fraction(1, 2): "5", Fraction(3, 4): "75"}[rest]


def standings(players, rounds, n, tiebreaks):
    counted = rounds[:n]
    outcome = {no: [] for no in players}  # per round: (points, opponent or None, over the board)
    for entries in counted:
        for e in entries:
            if e[0] == "bye":
                outcome[e[1]].append((BYES[e[2]], None, False))
            else:
                w, b, played = RESULTS[e[3]]
                outcome[e[1]].append((w, e[2], played))
                outcome[e[2]].append((b, e[1], played))
    points = {no: sum((o[0] for o in rs), Fraction(0)) for no, rs in outcome.items()}
    values = {}
    for no, rs in outcome.items():
        contrib = [points[q] if played else points[no] for _, q, played in rs]
        bh = sum(contrib, Fraction(0))
        sb = sum((points[q] if s == 1 else points[q] / 2 for s, q, played in rs if played and s > 0), Fraction(0))
        wins = sum(1 for s, q, played in rs if played and s == 1)
        values[no] = {"bh": bh, "bh1": bh - min(contrib), "sb": sb, "wins": Fraction(wins)}
    def key(no):
        return (points[no], *[values[no][tb] for tb in tiebreaks])
    order = sorted(players, key=lambda no: (tuple(-v for v in key(no)), no))
    rows = []
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and key(order[j + 1]) == key(order[i]):
            j += 1
        place = str(i + 1) if i == j else f"{i + 1}-{j + 1}"
        for no in order[i:j + 1]:
            rating, name = players[no]
            rows.append([place, str(no), name, "-" if rating == 0 else str(rating), number(points[no]),
                         *[number(values[no][tb]) for tb in tiebreaks]])
        i = j + 1
    return rows


def render(header, aligns, rows):
    table = [header] + rows
    widths = [max(len(r[c]) for r in table) for c in range(len(header))]
    out = []
    for r in table:
        cells = [cell.ljust(widths[c]) if aligns[c] == "L" else cell.rjust(widths[c]) for c, cell in enumerate(r)]
        out.append("  ".join(cells).rstrip(" "))
    return "".join(line + "\n" for line in out)


def command(args):
    options, plain = {}, []
    it = iter(args)
    for a in it:
        if a in ("--after-round", "--tiebreaks"):
            value = next(it, None)
            if value is None:
                raise Usage(f"{a} needs a value")
            if a in options:
                raise Usage(f"{a} given twice")
            options[a] = value
        elif a.startswith("-") and len(a) > 1:
            raise Usage(f'unknown option "{a}"')
        else:
            plain.append(a)
    after = None
    if "--after-round" in options:
        v = options["--after-round"]
        if not whole(v) or int(v) == 0:
            raise Usage(f'--after-round takes a round number, not "{v}"')
        after = int(v)
    tiebreaks = list(DEFAULT_TIEBREAKS)
    if "--tiebreaks" in options:
        v = options["--tiebreaks"]
        if v == "none":
            tiebreaks = []
        else:
            tiebreaks = v.split(",")
            for tb in tiebreaks:
                if tb not in TIEBREAKS:
                    raise Usage(f'unknown tiebreak "{tb}" (bh1, bh, sb, wins, or none)')
            if len(set(tiebreaks)) != len(tiebreaks):
                raise Usage("a tiebreak is listed twice")
    if len(plain) != 1:
        raise Usage("standings takes one FILE")
    path = plain[0]
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Failure(f"{path}: {e}")
    try:
        event, planned, players, rounds = parse(text)
    except Failure as e:
        raise Failure(f"{path}: {e}")
    if after is None:
        n = 0
        while n < len(rounds) and finished(rounds[n]):
            n += 1
        if n == 0:
            raise Failure(f"{path}: no finished rounds")
    else:
        if after > len(rounds):
            raise Failure(f"{path}: round {after} has not been paired")
        for k in range(after):
            if not finished(rounds[k]):
                raise Failure(f"{path}: round {k + 1} is not finished")
        n = after
    header = ["Place", "No", "Name", "Rating", "Pts", *[TIEBREAKS[tb] for tb in tiebreaks]]
    aligns = ["R", "R", "L", "R", "R", *["R"] * len(tiebreaks)]
    return (f"{event} - standings after round {n} of {planned}\n\n"
            + render(header, aligns, standings(players, rounds, n, tiebreaks)))


def main(argv):
    if not argv or argv[0] != "standings":
        print("reference.py implements only: standings [--after-round N] [--tiebreaks LIST] FILE", file=sys.stderr)
        return 2
    try:
        out = command(argv[1:])
    except Usage as e:
        print(f"td: {e}", file=sys.stderr)
        return 2
    except Failure as e:
        print(f"td: {e}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(out.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
