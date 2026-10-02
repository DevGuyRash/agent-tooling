

# ---------------------------------------------------------------- pagerlog replay

def layout(columns, rows):
    """A table the way pagerlog lays them out; columns are (header, "<" or ">")."""
    table = [[h for h, _ in columns]] + rows
    widths = [max(len(r[i]) for r in table) for i in range(len(columns))]
    return "".join("  ".join(f"{c:{a}{w}}" for c, (_, a), w in zip(r, columns, widths)).rstrip(" ") + "\n"
                   for r in table)


def replay_main(argv):
    """replay FILE HISTORY: the report of `pagerlog replay` (docs/replay.md), for a history export pagerlog has
    already checked."""
    path, history = argv
    try:
        routing = load(path)
    except RoutingError as e:
        print(e, file=sys.stderr)
        return 1
    with open(history, encoding="utf-8") as fh:
        lines = [l.rstrip("\r") for l in fh.read().split("\n")[1:]]
    before, after, groups, days, total = {}, {}, {}, [], 0
    for line in lines:
        if not line:
            continue
        time, name, receivers, labels = line.split("\t")
        labels = {} if labels == "-" else dict(item.split("=", 1) for item in labels.split(","))
        labels["alertname"] = name
        when = datetime.strptime(time, TIME_FORMAT).replace(tzinfo=timezone.utc)
        was = receivers.split(",")
        now = receivers_for(routing, labels, when)
        total += 1
        days.append(time[:10])
        for r in was:
            before[r] = before.get(r, 0) + 1
        for r in now:
            after[r] = after.get(r, 0) + 1
        if set(was) != set(now):
            key = (name, ", ".join(sorted(was)), ", ".join(sorted(now)))
            groups[key] = groups.get(key, 0) + 1
    out = f"Replay of {total} alerts ({min(days)} to {max(days)}) through {path}\n\n"
    rows = []
    for r in sorted(set(before) | set(after)):
        b, a = before.get(r, 0), after.get(r, 0)
        rows.append([r, str(b), str(a), f"{a - b:+d}" if a != b else "0"])
    out += layout([("Receiver", "<"), ("Before", ">"), ("After", ">"), ("Change", ">")], rows)
    changed = sum(groups.values())
    out += f"\nChanged: {changed} of {total} alerts\n"
    if changed:
        ordered = sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))
        out += "\n" + layout([("Alerts", ">"), ("Alert", "<"), ("Before", "<"), ("After", "<")],
                             [[str(n), *key] for key, n in ordered])
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay"]:
        sys.exit(replay_main(sys.argv[2:]))
    sys.exit(main(sys.argv[1:]))
