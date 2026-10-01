#!/usr/bin/env python3
"""Pick the backup snapshots the nightly prune deletes.

Reads a catalog exported by the storage server (one snapshot per line, tab-separated: id, host, set,
created, bytes, state, tags; blank lines and # comments ignored) and applies a retention policy to each
host/set series separately:

  --last N      keep the N newest snapshots
  --daily N     keep the newest snapshot of each of the N most recent days that have one
  --weekly N    the same for ISO 8601 weeks
  --monthly N   the same for calendar months
  --hourly N, --yearly N, --within DURATION   (bakctl prune) hours, years, and everything within
                DURATION (<n>w<n>d<n>h) of the newest snapshot

Days, weeks, and months are UTC. A snapshot is kept when any rule keeps it. Only snapshots in state "ok"
count; partial and failed uploads are always deleted. Snapshots created in the same second are ordered by
id, the smaller id first, as if it were newer.

Prints the ids to delete, one per line, in catalog order. With --json it prints every snapshot with its
decision and the rules that kept it, for checking a policy by hand.

--plan prints the plan bakctl prune shows (docs/prune.md), where pinned snapshots and uploads still in
progress are kept too; --ids with --plan prints only the ids it drops.

Used by ops/nightly-prune.sh and bakctl prune. Exit status: 0 success, 1 unreadable or invalid catalog, 2 usage error.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

FIELDS = ("id", "host", "set", "created", "bytes", "state", "tags")
STATES = ("ok", "partial", "failed")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})")
RULES = ("last", "daily", "weekly", "monthly")
EXTRA_RULES = ("hourly", "yearly")
PERIODS = {
    "hourly": lambda t: t.strftime("%Y-%m-%dT%H"),
    "daily": lambda t: t.strftime("%Y-%m-%d"),
    "weekly": lambda t: "%04d-W%02d" % t.isocalendar()[:2],
    "monthly": lambda t: t.strftime("%Y-%m"),
    "yearly": lambda t: t.strftime("%Y"),
}
DURATION = re.compile(r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?")
REASONS = ("pinned", "in-progress", "last", "within", "hourly", "daily", "weekly", "monthly", "yearly")


class CatalogError(Exception):
    """A catalog line that cannot be used; the message names the line."""


def parse_created(text):
    """A created field as an aware UTC datetime; ValueError when it is not RFC 3339 with a zone."""
    if not STAMP.fullmatch(text):
        raise ValueError(text)
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def read_catalog(lines, name):
    """The snapshots in a catalog, as dicts with the catalog's fields plus "when" (UTC) and "line"."""
    snapshots, seen = [], {}
    for number, raw in enumerate(lines, 1):
        line = raw.rstrip("\n").rstrip("\r")
        if not line.strip() or line.strip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != len(FIELDS):
            raise CatalogError(f"{name} line {number}: want {len(FIELDS)} tab-separated fields, got {len(fields)}")
        snap = dict(zip(FIELDS, fields))
        for field in ("id", "host", "set"):
            if not NAME.fullmatch(snap[field]):
                raise CatalogError(f"{name} line {number}: bad {field} {snap[field]!r}")
        try:
            snap["when"] = parse_created(snap["created"])
        except ValueError:
            raise CatalogError(f"{name} line {number}: bad created time {snap['created']!r}") from None
        if not snap["bytes"].isdigit():
            raise CatalogError(f"{name} line {number}: bad byte count {snap['bytes']!r}")
        if snap["state"] not in STATES:
            raise CatalogError(f"{name} line {number}: bad state {snap['state']!r} (want ok, partial, or failed)")
        if snap["id"] in seen:
            raise CatalogError(f"{name} line {number}: duplicate id {snap['id']} (first on line {seen[snap['id']]})")
        seen[snap["id"]] = number
        snap["line"] = number
        snap["pinned"] = snap["tags"] != "-" and "pinned" in snap["tags"].split(",")
        snapshots.append(snap)
    return snapshots


def decide(snapshots, policy):
    """{id: [rules that keep it]} for every snapshot, rules in RULES order; an empty list means delete.

    policy maps each rule in RULES to a count (0 turns the rule off)."""
    kept = {s["id"]: [] for s in snapshots}
    series = {}
    for s in snapshots:
        if s["state"] == "ok":
            series.setdefault((s["host"], s["set"]), []).append(s)
    for members in series.values():
        members.sort(key=lambda s: s["id"])
        members.sort(key=lambda s: s["when"], reverse=True)  # stable: newest first, ties by id
        for s in members[:policy["last"]]:
            kept[s["id"]].append("last")
        if policy.get("within"):
            for s in members:
                if s["when"] >= members[0]["when"] - policy["within"]:
                    kept[s["id"]].append("within")
        for rule, period in PERIODS.items():
            wanted, previous = policy.get(rule, 0), None
            for s in members:
                if wanted <= 0:
                    break
                key = period(s["when"])
                if key != previous:
                    kept[s["id"]].append(rule)
                    previous = key
                    wanted -= 1
    return kept


def human(n):
    if n < 1024:
        return f"{n} B"
    units = ["KiB", "MiB", "GiB", "TiB", "PiB"]
    v, i = n / 1024, 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}"


def plan(snapshots, policy, ids_only):
    """The bakctl prune plan (docs/prune.md) as text."""
    kept = decide(snapshots, policy)
    series = {}
    for s in snapshots:
        series.setdefault((s["host"].encode(), s["set"].encode()), []).append(s)
    blocks, ids, keep, drop, freed = [], [], 0, 0, 0
    for key in sorted(series):
        members = sorted(series[key], key=lambda s: s["id"].encode())
        members.sort(key=lambda s: s["when"], reverse=True)
        ok = [s for s in members if s["state"] == "ok"]
        lines, k = [], 0
        for s in members:
            reasons = set(kept[s["id"]])
            if s["pinned"]:
                reasons.add("pinned")
            if s["state"] == "partial" and (not ok or s["when"] > ok[0]["when"]):
                reasons.add("in-progress")
            ordered = [r for r in REASONS if r in reasons]
            if ordered:
                action, k = "keep", k + 1
            else:
                action, ordered = "drop", ["expired" if s["state"] == "ok" else s["state"]]
                ids.append(s["id"])
                freed += int(s["bytes"])
            lines.append(f"  {action}  {s['id']}  {s['when'].strftime('%Y-%m-%dT%H:%M:%SZ')}  {','.join(ordered)}")
        blocks.append(f"{key[0].decode()}/{key[1].decode()}: keep {k}, drop {len(members) - k}\n" + "\n".join(lines))
        keep, drop = keep + k, drop + len(members) - k
    if ids_only:
        return "".join(i + "\n" for i in ids)
    return "\n\n".join(blocks + [f"total: keep {keep}, drop {drop}, frees {human(freed)}"]) + "\n"


def duration(text):
    m = DURATION.fullmatch(text)
    if not text or not m:
        raise argparse.ArgumentTypeError(f"want a duration such as 36h, 2w, or 1w3d, got {text!r}")
    w, d, h = (int(g) if g else 0 for g in m.groups())
    return timedelta(weeks=w, days=d, hours=h)


def count(text):
    if not text.isdigit():
        raise argparse.ArgumentTypeError(f"want a whole number, got {text!r}")
    return int(text)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="retention.py", description="Pick the snapshots the nightly prune deletes.")
    for rule in RULES + EXTRA_RULES:
        parser.add_argument(f"--{rule}", type=count, default=0, metavar="N")
    parser.add_argument("--within", type=duration, default=timedelta(0), metavar="DURATION")
    parser.add_argument("--plan", action="store_true", help="print the bakctl prune plan")
    parser.add_argument("--ids", action="store_true", help="with --plan, print only the ids it drops")
    parser.add_argument("--host", help="only this host's series")
    parser.add_argument("--set", help="only this set's series")
    parser.add_argument("--json", action="store_true", help="print every snapshot and its decision")
    parser.add_argument("catalog", help="catalog file, or - for standard input")
    args = parser.parse_args(argv)
    policy = {rule: getattr(args, rule) for rule in RULES + EXTRA_RULES}
    policy["within"] = args.within
    if not any(policy.values()):
        parser.error("no keep rule given; refusing to delete every snapshot")

    try:
        if args.catalog == "-":
            snapshots = read_catalog(sys.stdin, "stdin")
        else:
            with open(args.catalog, encoding="utf-8") as fh:
                snapshots = read_catalog(fh, args.catalog)
    except (OSError, CatalogError) as exc:
        print(f"retention.py: {exc}", file=sys.stderr)
        return 1
    snapshots = [s for s in snapshots
                 if (args.host is None or s["host"] == args.host) and (args.set is None or s["set"] == args.set)]

    if args.plan:
        sys.stdout.write(plan(snapshots, policy, args.ids))
        return 0
    kept = decide(snapshots, policy)
    if args.json:
        rows = [{"id": s["id"], "host": s["host"], "set": s["set"],
                 "created": s["when"].strftime("%Y-%m-%dT%H:%M:%SZ"), "bytes": int(s["bytes"]),
                 "state": s["state"], "keep": bool(kept[s["id"]]), "rules": kept[s["id"]]} for s in snapshots]
        json.dump(rows, sys.stdout, indent=1)
        sys.stdout.write("\n")
    else:
        for s in snapshots:
            if not kept[s["id"]]:
                print(s["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
