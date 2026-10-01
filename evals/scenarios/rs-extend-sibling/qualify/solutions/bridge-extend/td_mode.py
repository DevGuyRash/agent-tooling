# td standings: td checks the command line and the file, works out the rounds to count, and runs
#     python3 tools/standings.py --td ROUNDS TIEBREAKS FILE
# with TIEBREAKS a comma-separated list (bh1, bh, sb, wins) or "none"; this prints the standings in the
# layout described in docs/standings.md.

TD_HEADERS = {"bh1": "BH1", "bh": "BH", "sb": "SB", "wins": "Wins"}


def td_rows(t, rounds, tiebreaks):
    t.rounds = t.rounds[:rounds]
    table = outcomes(t)
    points = {no: sum((o[0] for o in rs), Fraction(0)) for no, rs in table.items()}
    keyed = []
    for no, rs in table.items():
        contributions = [points[opp] if played else points[no] for _, opp, played in rs]
        bh = sum(contributions, Fraction(0))
        sb = Fraction(0)
        wins = 0
        for score, opp, played in rs:
            if played and score == 1:
                sb += points[opp]
                wins += 1
            elif played and score == HALF:
                sb += points[opp] / 2
        values = {"bh": bh, "bh1": bh - min(contributions, default=Fraction(0)), "sb": sb, "wins": Fraction(wins)}
        keyed.append((no, (points[no], *[values[tb] for tb in tiebreaks])))
    keyed.sort(key=lambda k: (tuple(-v for v in k[1]), k[0]))
    rows = []
    i = 0
    while i < len(keyed):
        j = i
        while j + 1 < len(keyed) and keyed[j + 1][1] == keyed[i][1]:
            j += 1
        place = str(i + 1) if i == j else f"{i + 1}-{j + 1}"
        for no, key in keyed[i:j + 1]:
            rating, name = t.players[no]
            rows.append([place, str(no), name, str(rating) if rating else "-", *[number(v) for v in key]])
        i = j + 1
    return rows


def td_main(argv):
    rounds, tiebreaks, path = int(argv[0]), argv[1], argv[2]
    tiebreaks = [] if tiebreaks == "none" else tiebreaks.split(",")
    with open(path, encoding="utf-8") as fh:
        t = parse(fh.read())
    planned, event = t.planned, t.event
    header = ["Place", "No", "Name", "Rating", "Pts", *[TD_HEADERS[tb] for tb in tiebreaks]]
    lines = [header] + td_rows(t, rounds, tiebreaks)
    widths = [max(len(r[c]) for r in lines) for c in range(len(header))]
    out = [f"{event} - standings after round {rounds} of {planned}", ""]
    for r in lines:
        out.append("  ".join(cell.ljust(widths[c]) if c == 2 else cell.rjust(widths[c]) for c, cell in enumerate(r)).rstrip())
    sys.stdout.buffer.write(("\n".join(out) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--td"]:
        sys.exit(td_main(sys.argv[2:]))
    sys.exit(main(sys.argv[1:]))
