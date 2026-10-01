#!/usr/bin/env python3
"""Live standings for the club website.

The nightly job on the club server runs

    python3 tools/standings.py --tsv tournaments/autumn-league-2026.trn > /srv/club/www/standings.tsv

and the standings page on the website reads that file. Without --tsv it prints a quick table for a look
by hand.

The standings are live: every game that has a result counts, including the finished games of a round still
in progress; a game not played yet (*) counts for neither player.

Points: a win, a forfeit win, and a full-point bye give 1; a draw and a half-point bye give 1/2; a loss, a
forfeit loss, a double forfeit, and a zero-point bye give 0.

Buchholz: the sum of the opponents' points, round by round. For a round in which the player did not play a
game over the board (any bye, a forfeit won or lost, a double forfeit), the player's own points count in
place of an opponent's. A round whose game is not played yet adds nothing.

Sonneborn-Berger: for each game won over the board, the opponent's points; for each draw, half the
opponent's points. Forfeits and byes add nothing.

Order: points, then Buchholz, then Sonneborn-Berger (higher first), then start number.

The file format is described in docs/format.md; this script assumes a file that `td check` accepts.
"""
import sys
from fractions import Fraction

HALF = Fraction(1, 2)

# result token -> (white's points, black's points, played over the board)
RESULTS = {
    "1-0": (Fraction(1), Fraction(0), True),
    "0-1": (Fraction(0), Fraction(1), True),
    "1/2": (HALF, HALF, True),
    "+-": (Fraction(1), Fraction(0), False),
    "-+": (Fraction(0), Fraction(1), False),
    "--": (Fraction(0), Fraction(0), False),
}
BYES = {"full": Fraction(1), "half": HALF, "zero": Fraction(0)}


class Tournament:
    def __init__(self):
        self.event = ""
        self.planned = 0
        self.players = {}  # start number -> (rating, name), in file order
        self.rounds = []  # each round: list of ("game", white, black, result) or ("bye", no, kind)


def parse(text):
    t = Tournament()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if fields[0] == "event":
            t.event = line[len("event"):].strip()
        elif fields[0] == "rounds":
            t.planned = int(fields[1])
        elif fields[0] == "player":
            t.players[int(fields[1])] = (int(fields[2]), " ".join(fields[3:]))
        elif fields[0] == "round":
            t.rounds.append([])
        elif fields[0] == "bye":
            t.rounds[-1].append(("bye", int(fields[1]), fields[2]))
        else:
            t.rounds[-1].append(("game", int(fields[0]), int(fields[1]), fields[2]))
    return t


def outcomes(t):
    """For each player, one entry per round: (points, opponent or None, played over the board), or None for
    a game not played yet."""
    table = {no: [] for no in t.players}
    for entries in t.rounds:
        for entry in entries:
            if entry[0] == "bye":
                _, no, kind = entry
                table[no].append((BYES[kind], None, False))
                continue
            _, white, black, result = entry
            if result == "*":
                table[white].append(None)
                table[black].append(None)
                continue
            w, b, played = RESULTS[result]
            table[white].append((w, black, played))
            table[black].append((b, white, played))
    return table


def standings(t):
    """Rows of (start number, name, rating, points, Buchholz, Sonneborn-Berger) in standings order."""
    table = outcomes(t)
    points = {no: sum((o[0] for o in rounds if o is not None), Fraction(0)) for no, rounds in table.items()}
    rows = []
    for no, rounds in table.items():
        buchholz = Fraction(0)
        sb = Fraction(0)
        for o in rounds:
            if o is None:
                continue
            score, opponent, played = o
            if not played:
                buchholz += points[no]
                continue
            buchholz += points[opponent]
            if score == 1:
                sb += points[opponent]
            elif score == HALF:
                sb += points[opponent] / 2
        rating, name = t.players[no]
        rows.append((no, name, rating, points[no], buchholz, sb))
    rows.sort(key=lambda r: (-r[3], -r[4], -r[5], r[0]))
    return rows


def number(x):
    """3, 3.5, 8.25: the shortest decimal form of a multiple of 1/4."""
    if x.denominator == 1:
        return str(x.numerator)
    return f"{float(x):g}"


def rounds_played(t):
    """Rounds with at least one result."""
    return sum(1 for entries in t.rounds if any(e[0] == "bye" or e[3] != "*" for e in entries))


def main(argv):
    tsv = "--tsv" in argv
    files = [a for a in argv if a != "--tsv"]
    if len(files) != 1 or files[0].startswith("-"):
        print("usage: standings.py [--tsv] FILE", file=sys.stderr)
        return 2
    try:
        with open(files[0], encoding="utf-8") as fh:
            t = parse(fh.read())
    except OSError as e:
        print(f"standings.py: {e}", file=sys.stderr)
        return 1
    rows = standings(t)
    if tsv:
        print("rank\tno\tname\trating\tpoints\tbuchholz\tsonneborn_berger")
        for rank, (no, name, rating, pts, bh, sb) in enumerate(rows, 1):
            print(f"{rank}\t{no}\t{name}\t{rating}\t{number(pts)}\t{number(bh)}\t{number(sb)}")
        return 0
    print(f"{t.event} (live, {rounds_played(t)} of {t.planned} rounds)")
    width = max((len(r[1]) for r in rows), default=0)
    for rank, (no, name, rating, pts, bh, sb) in enumerate(rows, 1):
        print(f"{rank:>3}. {name:<{width}}  {number(pts):>4}  BH {number(bh):>5}  SB {number(sb):>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
