#!/usr/bin/env python3
"""Regenerate hidden/cases.json for revise-wrapper-go: hidden crossing logs, command lines, and what the fixture's
own ferry prints for each (the current tool, punctuality included, which runs scripts/punctuality.py through
python3). The ticket asks for exactly that output, so the fixture's build is the reference.

    python3 hidden/make_cases.py

It builds the fixture offline in a private temporary directory outside every repository with the host's Go
(TRIAL_GOROOT or the GOROOT `go env` reports), runs every case with the case's files in its working directory and
python3 on PATH, and fails unless model.py, written from docs/punctuality.md, gives the same output for every
punctuality case, and unless each careless port model.py describes (VARIANTS) differs from it on at least one
case. Deterministic: the data come from fixed seeds.
"""
import base64
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
sys.path.insert(0, str(HERE))
import model  # noqa: E402

DIR = "{dir}"
DAYS = [f"2026-10-{d:02d}" for d in range(5, 12)]

# pier -> [(route, departures, profile)]; a profile is (early, on time, late, very late, cancelled) weights.
SOUND = (0.1, 0.9, 0, 0, 0.02)
FAIR = (0.08, 0.72, 0.17, 0.03, 0.03)
POOR = (0.03, 0.45, 0.4, 0.12, 0.06)
FLEET = {
    "inchmara": [("Inchmara–Dunvoan", ["07:30", "09:00", "11:00", "13:30", "16:00", "18:30"], FAIR),
                 ("Inchmara–Saltness", ["08:10", "12:10", "15:40", "19:10"], FAIR),
                 ("Inchmara–Port Ardain", ["10:20", "17:20"], SOUND)],
    "torrisdale": [("Torrisdale–Bàgh Mòr", ["07:00", "12:00", "17:00"], POOR),
                   ("Torrisdale–Saltness", ["09:40", "16:40"], SOUND)],
    "dunvoan": [("Dunvoan–Inchmara", ["08:15", "10:00", "12:15", "14:45", "17:15", "19:30"], FAIR),
                ("Dunvoan–Kilbride", ["09:20", "13:50", "17:40"], POOR)],
    "craigmhor": [("Craigmhor–Port Ardain", ["06:40", "09:40", "12:40", "15:40", "18:40"], SOUND),
                  ("Craigmhor–Bàgh Mòr", ["11:10"], FAIR)],
    "saltness": [("Saltness–Inchmara", ["06:50", "10:50", "14:20", "17:50"], FAIR),
                 ("Saltness–Torrisdale", ["08:00", "15:00"], SOUND)],
    "kilbride": [("Kilbride–Dunvoan", ["07:45", "11:45", "16:10"], FAIR),
                 ("Kilbride–Eilean Rùm", ["10:30", "23:50"], POOR)],
    "bagh-mor": [("Bàgh Mòr–Torrisdale", ["08:30", "13:30", "18:30"], POOR),
                 ("Bàgh Mòr–Craigmhor", ["12:30"], None)],  # the ramp is out: every sailing cancelled
    "port-ardain": [("Port Ardain–Craigmhor", ["07:50", "10:50", "13:50", "16:50", "19:50"], SOUND),
                    ("Port Ardain–Inchmara", ["11:40", "18:40"], SOUND)],
    "eilean-rum": [("Eilean Rùm–Kilbride", ["00:10", "06:30", "15:15"], FAIR)],
}


def hm(m):
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def pier_logs(seed, fleet=FLEET, days=DAYS):
    """{pier: [(date, route, scheduled, departed), ...]} for each pier, sailing by sailing."""
    rng = random.Random(seed)
    out = {}
    for pier, routes in fleet.items():
        rows = []
        for day in days:
            for route, deps, profile in routes:
                for dep in deps:
                    if profile is None or rng.random() < profile[4]:
                        rows.append((day, route, dep, "cancelled"))
                        continue
                    kind = rng.choices(range(4), weights=profile[:4])[0]
                    d = [rng.choice([-1, -2, -3, -4, -6, -7]), rng.randint(0, 5), rng.randint(6, 25),
                         rng.randint(26, 70)][kind]
                    if dep == "00:10" and rng.random() < 0.3:
                        d = -rng.randint(8, 14)  # left before midnight
                    rows.append((day, route, dep, hm(minutes(dep) + d)))
        out[pier] = rows
    return out


def minutes(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def log_text(pier, rows):
    return "".join([f"# {pier} pier ticket office\n"] + [f"{d}\t{r}\t{s}\t{x}\n" for d, r, s, x in rows])


def ties_case():
    """Sixteen routes that ran on time every time (equal shares, which must keep their first-seen order), one
    that did not, and one where nothing ran."""
    names = ["Tobar–Sgùrr", "Rònach–Lìonag", "Àird–Bealach", "Cille–Dùn", "Mòine–Gleann", "Sgeir–Tràigh",
             "Caolas–Rubha", "Cnoc–Lochan", "Beinn–Eas", "Dail–Achadh", "Inbhir–Coire", "Allt–Srath",
             "Bàgh–Ceann", "Port–Òban", "Druim–Fèith", "Cùl–Machair"]
    rows = []
    rng = random.Random(7)
    for i in range(3):
        for j, n in enumerate(names):
            rows.append(("2026-10-05", n, f"{6 + i * 4:02d}:{j * 3:02d}", hm(6 * 60 + i * 240 + j * 3 + rng.randint(-3, 5))))
        rows.append(("2026-10-05", "Sgùrr–Tobar", f"{7 + i * 4:02d}:00", hm(7 * 60 + i * 240 + [3, 12, 40][i])))
        rows.append(("2026-10-05", "Lìonag–Rònach", f"{8 + i * 4:02d}:30", "cancelled"))
    return rows


def early_case():
    """A route where every sailing left early, one with even counts whose middle delays straddle zero, and
    equal shares from different counts (9 of 10 and 18 of 20 on time)."""
    d = "2026-10-06"
    rows = [(d, "Saltness–Torrisdale", f"{h:02d}:00", hm(h * 60 - k)) for h, k in [(8, 1), (10, 6), (12, 2), (14, 11)]]
    rows += [(d, "Torrisdale–Saltness", f"{h:02d}:30", hm(h * 60 + 30 + k)) for h, k in [(8, -2), (10, 1), (12, -3), (14, 2)]]
    nine = [0, 1, 2, 3, 4, 5, 1, 2, 0, 9]
    eighteen = nine + [5, 4, 3, 2, 1, 0, -1, -2, 30, 0]
    rows += [(d, "Craigmhor–Port Ardain", f"{6 + i:02d}:40", hm((6 + i) * 60 + 40 + k)) for i, k in enumerate(nine)]
    rows += [(d, "Port Ardain–Craigmhor", f"{6 + i // 2:02d}:{(i % 2) * 30 + 5:02d}",
              hm((6 + i // 2) * 60 + (i % 2) * 30 + 5 + k)) for i, k in enumerate(eighteen)]
    return rows


def zero_share_case():
    """A route whose every sailing that ran left late (a share of 0), seen before a route whose every sailing was
    cancelled, which must still come first."""
    d = "2026-10-07"
    return [(d, "Saltness–Inchmara", "06:50", "07:02"), (d, "Inchmara–Dunvoan", "07:30", "07:31"),
            (d, "Inchmara–Dunvoan", "09:00", "09:00"), (d, "Dunvoan–Kilbride", "09:20", "09:24"),
            (d, "Inchmara–Port Ardain", "10:20", "cancelled"), (d, "Saltness–Inchmara", "10:50", "cancelled"),
            (d, "Inchmara–Dunvoan", "11:00", "11:09"), (d, "Dunvoan–Kilbride", "13:50", "14:20"),
            (d, "Saltness–Inchmara", "14:20", "14:31"), (d, "Inchmara–Port Ardain", "17:20", "cancelled")]


def close_shares_case():
    """Shares less than a whole percent apart: 5 of 9 on time (a tenth sailing cancelled), seen first, then 11 of
    20 and 6 of 11. Exact shares order them 6/11, 11/20, 5/9; whole percents (55, 55, 54) or rounded ones (56, 55,
    55) would put two of them the other way round."""
    d = "2026-10-08"
    plan = {  # route: (first departure, minutes between, delays in order; None for a cancelled sailing)
        "Kilbride–Dunvoan": ("06:05", 60, [2, 9, 0, 14, 5, None, 7, -1, 22, 3]),
        "Torrisdale–Bàgh Mòr": ("06:20", 30, [0, 6, 1, 8, 3, 12, 5, 3, 17, -2, 9, 0, 31, 2, 11, 5, 7, 1, 10, 4]),
        "Craigmhor–Port Ardain": ("06:40", 60, [1, 8, 0, 12, -3, 6, 4, 19, 2, 7, 5]),
    }
    shares = {}
    rows = []
    for route, (first, step, delays) in plan.items():
        ran = [x for x in delays if x is not None]
        shares[route] = (sum(1 for x in ran if x <= 5), len(ran))
        for k, x in enumerate(delays):
            sched = minutes(first) + k * step
            rows.append((sched, d, route, hm(sched), "cancelled" if x is None else hm(sched + x)))
    assert list(shares.values()) == [(5, 9), (11, 20), (6, 11)], shares
    return [r[1:] for r in sorted(rows)]


def b64(data):
    return base64.b64encode(data).decode()


def build_cases():
    cases = []

    def add(name, args, files, kind="punctuality"):
        cases.append({"name": name, "kind": kind, "args": args, "files": files})

    sample = {p.name: p.read_text(encoding="utf-8") for p in sorted((FIXTURE / "logs").glob("*.log"))}
    sample_args = [f"{DIR}/{n}" for n in sample]
    add("docs-example", ["punctuality", "--from", "2026-09-14", "--to", "2026-09-14", *sample_args], sample)
    add("sample-week", ["punctuality", *sample_args], sample)

    week = pier_logs(1005)
    files = {f"{p}.log": log_text(p.replace("-", " ").title(), rows) for p, rows in week.items()}
    order = ["kilbride.log", "craigmhor.log", "inchmara.log", "bagh-mor.log", "dunvoan.log", "eilean-rum.log",
             "torrisdale.log", "port-ardain.log", "saltness.log"]
    fleet_args = [f"{DIR}/{n}" for n in order]
    add("fleet-week", ["punctuality", *fleet_args], files)
    add("fleet-midweek", ["punctuality", "--from", "2026-10-07", "--to", "2026-10-09", *fleet_args], files)
    add("fleet-from", ["punctuality", "--from", "2026-10-10", *fleet_args], files)
    add("fleet-to", ["punctuality", "--to", "2026-10-05", *fleet_args], files)
    add("fleet-other-order", ["punctuality", *reversed(fleet_args)], files)
    add("fleet-no-such-days", ["punctuality", "--from", "2026-11-01", *fleet_args], files)

    add("ties", ["punctuality", f"{DIR}/ties.log"], {"ties.log": log_text("Rònach", ties_case())})
    add("early", ["punctuality", f"{DIR}/early.log"], {"early.log": log_text("Saltness", early_case())})
    add("zero-share", ["punctuality", f"{DIR}/inchmara.log"],
        {"inchmara.log": log_text("Inchmara", zero_share_case())})
    add("close-shares", ["punctuality", f"{DIR}/kilbride.log"],
        {"kilbride.log": log_text("Kilbride", close_shares_case())})
    add("only-cancelled", ["punctuality", f"{DIR}/ramp.log"],
        {"ramp.log": log_text("Bàgh Mòr", [("2026-10-05", "Bàgh Mòr–Craigmhor", "12:30", "cancelled")])})
    add("comments-only", ["punctuality", f"{DIR}/quiet.log"], {"quiet.log": "# Craigmhor pier ticket office\n# no sailings: storm\n\n"})

    bad = log_text("Dunvoan", week["dunvoan"][:2]) + "2026-10-05\tDunvoan–Inchmara\t10:00\tlate\n"
    add("bad-log", ["punctuality", f"{DIR}/inchmara.log", f"{DIR}/bad.log"],
        {"inchmara.log": files["inchmara.log"], "bad.log": bad})
    add("missing-log", ["punctuality", f"{DIR}/nowhere.log"], {})
    add("bad-date", ["punctuality", "--from", "2026-10-32", f"{DIR}/inchmara.log"], {"inchmara.log": files["inchmara.log"]})
    add("dates-reversed", ["punctuality", "--from", "2026-10-09", "--to", "2026-10-07", f"{DIR}/inchmara.log"],
        {"inchmara.log": files["inchmara.log"]})
    add("unknown-flag", ["punctuality", "--since", "2026-10-07", f"{DIR}/inchmara.log"], {"inchmara.log": files["inchmara.log"]})
    add("no-logs", ["punctuality", "--from", "2026-10-07"], {})

    # ferry's other commands, which the change must leave as they are.
    add("check-fleet", ["check", *fleet_args[:4]], files, kind="existing")
    add("check-bad", ["check", f"{DIR}/bad.log", f"{DIR}/inchmara.log"],
        {"inchmara.log": files["inchmara.log"], "bad.log": bad}, kind="existing")
    add("day-fleet", ["day", "2026-10-08", *fleet_args], files, kind="existing")
    add("day-midnight", ["day", "2026-10-06", f"{DIR}/eilean-rum.log", f"{DIR}/kilbride.log"], files, kind="existing")
    add("day-none", ["day", "2026-12-25", *fleet_args[:2]], files, kind="existing")
    add("day-usage", ["day", f"{DIR}/kilbride.log"], files, kind="existing")
    return cases


def build_fixture(tmp):
    goroot = os.environ.get("TRIAL_GOROOT") or subprocess.run(
        ["go", "env", "GOROOT"], capture_output=True, text=True, check=True, cwd="/",
        env=dict(os.environ, GOTOOLCHAIN="local")).stdout.strip()
    src = Path(tmp) / "ferry"
    shutil.copytree(FIXTURE, src)
    env = {"PATH": f"{goroot}/bin:/usr/bin:/bin", "HOME": str(tmp), "GOROOT": goroot, "GOCACHE": f"{tmp}/gocache",
           "GOPATH": f"{tmp}/gopath", "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOFLAGS": "-buildvcs=false",
           "GOWORK": "off", "LANG": "C.UTF-8"}
    subprocess.run([f"{goroot}/bin/go", "build", "-o", "ferry", "./cmd/ferry"], cwd=src, env=env, check=True)
    return src / "ferry"


def run_case(binary, case, work):
    work.mkdir(parents=True)
    for name, text in case["files"].items():
        (work / name).write_text(text, encoding="utf-8")
    args = [a.replace(DIR, str(work)) for a in case["args"]]
    r = subprocess.run([str(binary), *args], cwd=work, capture_output=True, timeout=120,
                       env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(work)})
    return r.returncode, r.stdout.replace(str(work).encode(), DIR.encode()), r.stderr.decode("utf-8", "replace")


STDERR_HAS = {  # fragments of the fixture's messages a port must keep (file and line; what is wrong)
    "bad-log": ["bad.log:4:", "bad departure"], "missing-log": ["nowhere.log", "no such file"],
    "bad-date": ["bad date", "usage: ferry"], "dates-reversed": ["after", "usage: ferry"],
    "unknown-flag": ["since"], "no-logs": ["usage: ferry"], "check-bad": ["bad.log:4:"],
    "day-usage": ["usage: ferry"],
}


def main():
    cases = build_cases()
    out, store = [], {}
    with tempfile.TemporaryDirectory(prefix="revise-wrapper-go-") as tmp:
        binary = build_fixture(tmp)
        for i, case in enumerate(cases):
            rc, stdout, stderr = run_case(binary, case, Path(tmp) / "cases" / f"{i:03d}")
            for frag in STDERR_HAS.get(case["name"], []):
                assert frag in stderr, (case["name"], frag, stderr)
            refs = {}
            for name, text in case["files"].items():
                data = text.encode("utf-8")
                key = hashlib.sha256(data).hexdigest()[:16]
                store[key] = b64(data)
                refs[name] = key
            entry = {"name": case["name"], "kind": case["kind"], "args": case["args"], "files": refs, "rc": rc,
                     "stdout_b64": b64(stdout)}
            if case["name"] in STDERR_HAS:
                entry["stderr_has"] = STDERR_HAS[case["name"]]
            out.append(entry)
            if case["kind"] == "punctuality" and rc == 0:
                want = model.output_for(case, model.Variant())
                assert want.encode() == stdout, f"model and fixture differ on {case['name']}:\n{want}\n{stdout.decode()}"
    ok = [(c, e) for c, e in zip(cases, out) if c["kind"] == "punctuality" and e["rc"] == 0]
    for variant in model.VARIANTS:
        caught = [c["name"] for c, e in ok if model.output_for(c, variant).encode() != base64.b64decode(e["stdout_b64"])]
        assert caught, f"no case tells {variant} apart"
        print(f"{variant.name}: caught by {', '.join(caught)}")
    doc = {"files": dict(sorted(store.items())), "cases": out}
    (HERE / "cases.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(out)} cases, {len(store)} distinct files written")


if __name__ == "__main__":
    main()
