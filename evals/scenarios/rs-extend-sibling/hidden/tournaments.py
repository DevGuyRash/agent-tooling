"""Deterministic tournament files for the scenario: a simple Swiss pairing (score groups, no repeat
pairings where avoidable, a full-point bye for the lowest unpaired player), rating-weighted random results,
and per-round special events. make_cases.py builds the hidden tournaments with it; the fixture's
tournaments/*.trn were written with it once (see make_cases.py --fixture).
"""
import random


def swiss(event, planned, players, played, seed, special=None, pending=None, crlf=False, header=None):
    """Text of a .trn file.

    players: [(no, rating, name)]. played: how many rounds to write. special: {round: [(kind, no), ...]}
    with kind "half" (half-point bye), "absent" (zero-point bye this round), "withdraw" (zero-point byes
    from this round on), "forfeit" (no loses its game by forfeit), "double" (no's game is a double forfeit).
    pending: {round: [board index, ...]} games written as * (boards counted from 0, in pairing order).
    """
    rng = random.Random(seed)
    special = special or {}
    pending = pending or {}
    score = {no: 0.0 for no, _, _ in players}
    rating = {no: r for no, r, _ in players}
    whites = {no: 0 for no, _, _ in players}
    met = {no: set() for no, _, _ in players}
    had_bye = set()
    withdrawn = set()
    lines = list(header or ["# Rookhaven Chess Club"]) + [f"event {event}", f"rounds {planned}", ""]
    for no, r, name in players:
        lines.append(f"player {no} {r} {name}")
    for rnd in range(1, played + 1):
        lines += ["", f"round {rnd}"]
        events = special.get(rnd, [])
        byes = []
        for kind, no in events:
            if kind == "withdraw":
                withdrawn.add(no)
        for no in sorted(withdrawn):
            byes.append((no, "zero"))
        for kind, no in events:
            if kind == "half":
                byes.append((no, "half"))
            elif kind == "absent":
                byes.append((no, "zero"))
        out = {no for no, _ in byes}
        active = [no for no, _, _ in players if no not in out]
        active.sort(key=lambda no: (-score[no], -rating[no], no))
        if len(active) % 2:
            pick = next(no for no in reversed(active) if no not in had_bye)
            active.remove(pick)
            had_bye.add(pick)
            byes.append((pick, "full"))
        games = []
        for a, b in _pair(active, score, met):
            met[a].add(b)
            met[b].add(a)
            white, black = (a, b) if whites[a] <= whites[b] else (b, a)
            whites[white] += 1
            games.append([white, black, None])
        for board, g in enumerate(games):
            white, black = g[0], g[1]
            if board in pending.get(rnd, []):
                g[2] = "*"
                continue
            diff = (rating[white] or 1500) - (rating[black] or 1500)
            expect = 1 / (1 + 10 ** (-diff / 400))
            x = rng.random()
            draw = 0.28
            if x < draw:
                g[2] = "1/2"
            elif x < draw + (1 - draw) * expect:
                g[2] = "1-0"
            else:
                g[2] = "0-1"
        for kind, no in events:
            for g in games:
                if no in (g[0], g[1]):
                    if kind == "forfeit":
                        g[2] = "-+" if no == g[0] else "+-"
                    elif kind == "double":
                        g[2] = "--"
        points = {"1-0": (1, 0), "0-1": (0, 1), "1/2": (0.5, 0.5), "+-": (1, 0), "-+": (0, 1), "--": (0, 0), "*": (0, 0)}
        for white, black, result in games:
            w, b = points[result]
            score[white] += w
            score[black] += b
            lines.append(f"{white} {black} {result}")
        for no, kind in byes:
            score[no] += {"full": 1, "half": 0.5, "zero": 0}[kind]
            lines.append(f"bye {no} {kind}")
    text = "\n".join(lines) + "\n"
    return text.replace("\n", "\r\n") if crlf else text


def _pair(ranked, score, met):
    """Pairs for players in ranking order: score group by score group (an odd player floats down), top
    half against bottom half, trying the next opponent down when two have met; a group that cannot be
    paired without a repeat takes the first opponent left."""
    pairs, left, carry = [], list(ranked), []
    while left:
        top = score[left[0]]
        group = carry + [no for no in left if score[no] == top]
        left = [no for no in left if score[no] != top]
        carry = [group.pop()] if len(group) % 2 else []
        half = len(group) // 2
        s1, s2 = group[:half], group[half:]
        for a in s1:
            b = next((x for x in s2 if x not in met[a]), s2[0])
            s2.remove(b)
            pairs.append((a, b))
    if carry:
        raise ValueError("odd number of players to pair")
    return pairs
