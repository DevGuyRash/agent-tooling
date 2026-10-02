#!/usr/bin/env python3
"""Regenerate hidden/cases.json for revise-wrapper-rs: hidden exports and units files, command lines, and what
the fixture's own froid prints for each (the current tool, digest included, which runs tools/digest.py through
python3). The ticket asks for exactly that output, so the fixture's build is the reference.

    python3 hidden/make_cases.py

It builds the fixture (Cargo.toml.in renamed) offline in a private temporary directory outside every repository
with the host's Rust toolchain (TRIAL_RUST_SYSROOT or `rustc --print sysroot`), runs every case with the case's
files in its working directory and python3 on PATH, and fails unless model.py, written from docs/digest.md,
gives the same digest for every case, and unless each careless port model.py describes (VARIANTS) differs from
it on at least one required case. Deterministic: the data come from fixed seeds.
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


def deg(t):
    return f"{t / 10:.1f}"


def export(rows, title="export from the logger gateway"):
    return "".join([f"# {title}\n"] + [f"{d}T{c}Z\t{u}\t{deg(t)}\n" for d, c, u, t in rows])


def units_file(ranges, extra=()):
    lines = ["# unit\tlow\thigh\n"] + [f"{u}\t{deg(lo)}\t{deg(hi)}\n" for u, (lo, hi) in ranges.items()]
    return "".join(lines + list(extra))


RANGES = {
    "comptoir-réfrigéré": (0, 40), "congélateur-3": (-250, -180), "frigo-légumes": (10, 60),
    "chambre-froide-2": (0, 40), "congélateur-viande": (-280, -200), "frigo-boulangerie": (0, 50),
}
CENTRES = {"comptoir-réfrigéré": (31, 9), "congélateur-3": (-205, 12), "frigo-légumes": (38, 14),
           "chambre-froide-2": (18, 10), "congélateur-viande": (-232, 15), "frigo-boulangerie": (29, 12)}
# First-seen order of the generated week, far from alphabetical; the widest name has two accented letters.
ORDER = ["frigo-légumes", "congélateur-3", "comptoir-réfrigéré", "chambre-froide-2", "frigo-boulangerie",
         "congélateur-viande"]
DAYS = [f"2026-10-{d:02d}" for d in range(5, 12)]


def week(seed, step=30, units=ORDER, days=DAYS):
    """{day: [(day, clock, unit, tenths), ...]} readings every `step` minutes, with defrost cycles on the freezers
    and door traffic on the fridges."""
    rng = random.Random(seed)
    state = {u: CENTRES[u][0] for u in units}
    out = {}
    for day in days:
        rows = []
        for slot in range(24 * 60 // step):
            hh, mm = divmod(slot * step, 60)
            for u in units:
                centre, spread = CENTRES[u]
                t = max(centre - spread, min(centre + spread, state[u] + rng.randint(-4, 4)))
                state[u] = t
                if u.startswith("congélateur") and mm == 0 and hh in (4, 16):
                    t = RANGES[u][1] + rng.randint(-6, 14)  # defrost
                elif not u.startswith("congélateur") and 10 <= hh <= 14 and rng.random() < 0.08:
                    t = RANGES[u][1] + rng.randint(1, 20)  # door open
                rows.append((day, f"{hh:02d}:{mm:02d}", u, t))
        out[day] = rows
    return out


def halves_day():
    """A day whose means and medians fall exactly halfway between two tenths, above and below zero, beside an even
    and an odd tenth, so rounding halves away from zero, or toward it, shows."""
    d = "2026-10-06"
    spec = {
        "congélateur-3": [-190, -175, -177, -196],        # mean -184.5, median -183.5
        "comptoir-réfrigéré": [21, 24, 26, 19],           # mean 22.5, median 22.5
        "frigo-légumes": [45, 46, 43, 44, 41, 48],        # mean 44.5, median 44.5
        "congélateur-viande": [-225, -226, -228, -227],   # mean -226.5, median -226.5
        "frigo-boulangerie": [15, 18, 19, 17],            # mean 17.25, median 17.5
        "chambre-froide-2": [-3, 0, -2, 0],               # mean -1.25, median -1.0
    }
    rows = []
    for i in range(6):
        for u in ["comptoir-réfrigéré", "congélateur-3", "frigo-légumes", "congélateur-viande",
                  "frigo-boulangerie", "chambre-froide-2"]:
            if i < len(spec[u]):
                rows.append((d, f"{6 + i:02d}:00", u, spec[u][i]))
    return rows


def ties_day():
    """Equally bad readings: the worst is the first of them in the exports, which a running maximum that
    replaces on equality, or Rust's max_by_key, gets wrong."""
    d = "2026-10-07"
    return [
        (d, "02:00", "frigo-boulangerie", 57), (d, "02:30", "frigo-boulangerie", -7),
        (d, "03:00", "frigo-boulangerie", 57), (d, "03:30", "frigo-boulangerie", 31),
        (d, "04:00", "congélateur-3", -171), (d, "04:15", "congélateur-3", -171), (d, "04:30", "congélateur-3", -259),
        (d, "05:00", "frigo-légumes", 4), (d, "05:30", "frigo-légumes", 66), (d, "06:00", "frigo-légumes", 66),
    ]


def near_zero_day():
    """A walk-in cooler hovering at zero: readings just below zero, a -0.0 from one logger, and a mean between
    -0.05 and 0 that the digest prints as 0.0."""
    d = "2026-10-08"
    temps = [0, -1, 0, 0, -1, 2, -2, 0, 0, 1, -1, 0]   # sum -2 over 12: mean -0.1667 tenths
    rows = [(d, f"{h:02d}:00", "chambre-froide-2", t) for h, t in enumerate(temps)]
    cold = [-4, -3, -5, -4]                             # mean -4.0, median -4.0: -0.4
    rows += [(d, f"{h:02d}:30", "frigo-boulangerie", t) for h, t in enumerate(cold)]
    return rows


def b64(data):
    return base64.b64encode(data).decode()


def build_cases():
    cases = []

    def add(name, args, files, kind="digest"):
        cases.append({"name": name, "kind": kind, "args": args, "files": files})

    sample = {"units.tsv": (FIXTURE / "data/units.tsv").read_text(encoding="utf-8"),
              "2026-09-21.log": (FIXTURE / "data/2026-09-21.log").read_text(encoding="utf-8"),
              "2026-09-22.log": (FIXTURE / "data/2026-09-22.log").read_text(encoding="utf-8")}
    add("docs-example", ["digest", "--units", f"{DIR}/units.tsv", "--day", "2026-09-21", f"{DIR}/2026-09-21.log"], sample)
    add("sample-both-days", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/2026-09-22.log", f"{DIR}/2026-09-21.log"], sample)

    wk = week(41)
    week_files = {"units.tsv": units_file(RANGES)}
    for day in DAYS:
        week_files[f"{day}.log"] = export(wk[day])
    shuffled = [f"{DIR}/{d}.log" for d in ["2026-10-09", "2026-10-05", "2026-10-11", "2026-10-07", "2026-10-06",
                                            "2026-10-10", "2026-10-08"]]
    add("week", ["digest", "--units", f"{DIR}/units.tsv", *shuffled], week_files)
    add("week-one-day", ["digest", "--units", f"{DIR}/units.tsv", "--day", "2026-10-08", *shuffled], week_files)
    add("week-no-such-day", ["digest", "--units", f"{DIR}/units.tsv", "--day", "2026-10-30", *shuffled], week_files)

    add("halves", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/halves.log"],
        {"units.tsv": units_file(RANGES), "halves.log": export(halves_day())})
    add("ties", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/ties.log"],
        {"units.tsv": units_file(RANGES), "ties.log": export(ties_day())})
    near = export(near_zero_day()).replace("\tchambre-froide-2\t0.0\n", "\tchambre-froide-2\t-0.0\n", 1)
    add("near-zero", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/cooler.log"],
        {"units.tsv": units_file(RANGES), "cooler.log": near})

    # A unit the units file does not list, among listed ones; the units file lists units no export has.
    stray = [(r[0], r[1], "frigo-cave" if r[2] == "frigo-légumes" else r[2], r[3]) for r in wk["2026-10-09"]]
    add("unit-without-range", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/stray.log"],
        {"units.tsv": units_file({**RANGES, "congélateur-réserve": (-250, -180)}), "stray.log": export(stray)})

    # A logger's backlog uploaded the next day: its readings come after the others, out of time order, in a
    # second file; days still come in order and readings keep their order in the exports.
    day1, day2 = wk["2026-10-05"], wk["2026-10-06"]
    late = [r for r in day1 if r[2] == "congélateur-3" and r[1] >= "15:00"]
    first = [r for r in day1 if r not in late]
    add("backlog", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/a.log", f"{DIR}/b.log"],
        {"units.tsv": units_file(RANGES), "a.log": export(first), "b.log": export(day2 + list(reversed(late)), "backlog")})

    add("comments-only", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/empty.log"],
        {"units.tsv": units_file(RANGES), "empty.log": "# export from the logger gateway\n# gateway offline\n\n"})
    one = [("2026-10-09", "07:45", "frigo-boulangerie", 33)]
    add("one-reading", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/one.log"],
        {"units.tsv": units_file(RANGES), "one.log": export(one)})
    one_out = [("2026-10-09", "07:45", "frigo-boulangerie", 33), ("2026-10-09", "08:00", "frigo-boulangerie", 51),
               ("2026-10-10", "08:00", "frigo-boulangerie", 49)]
    add("one-out", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/one.log"],
        {"units.tsv": units_file(RANGES), "one.log": export(one_out)})

    # Errors froid reports before any digest is made.
    bad = export(wk["2026-10-05"][:2]) + "2026-10-05T00:30Z\tfrigo-légumes\t3,8\n"
    add("bad-export", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/w.log", f"{DIR}/bad.log"],
        {"units.tsv": units_file(RANGES), "w.log": export(wk["2026-10-06"]), "bad.log": bad})
    add("missing-export", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/nowhere.log"], {"units.tsv": units_file(RANGES)})
    add("bad-units", ["digest", "--units", f"{DIR}/units.tsv", f"{DIR}/one.log"],
        {"units.tsv": units_file(RANGES, ["frigo-cave\t8.0\t2.0\n"]), "one.log": export(one)})
    add("bad-day", ["digest", "--units", f"{DIR}/units.tsv", "--day", "2026-10-32", f"{DIR}/one.log"],
        {"units.tsv": units_file(RANGES), "one.log": export(one)})
    add("unknown-option", ["digest", "--unit", f"{DIR}/units.tsv", f"{DIR}/one.log"],
        {"units.tsv": units_file(RANGES), "one.log": export(one)})
    add("no-exports", ["digest", "--units", f"{DIR}/units.tsv"], {"units.tsv": units_file(RANGES)})

    # froid's other commands, which the change must leave as they are.
    add("check-week", ["check", *shuffled[:3]], week_files, kind="existing")
    add("check-bad", ["check", f"{DIR}/bad.log", f"{DIR}/w.log"],
        {"w.log": export(wk["2026-10-06"]), "bad.log": bad}, kind="existing")
    add("latest-week", ["latest", "--units", f"{DIR}/units.tsv", *shuffled], week_files, kind="existing")
    latest_rows = [("2026-10-09", "07:45", "frigo-cave", 94), ("2026-10-09", "07:45", "congélateur-3", -262),
                   ("2026-10-09", "07:30", "frigo-légumes", 71), ("2026-10-09", "07:45", "frigo-légumes", 52),
                   ("2026-10-09", "07:45", "frigo-légumes", 53), ("2026-10-09", "07:15", "frigo-légumes", 99)]
    add("latest-status", ["latest", "--units", f"{DIR}/units.tsv", f"{DIR}/l.log"],
        {"units.tsv": units_file(RANGES), "l.log": export(latest_rows)}, kind="existing")
    add("latest-usage", ["latest", "--units"], {}, kind="existing")
    return cases


def build_fixture(tmp):
    sysroot = os.environ.get("TRIAL_RUST_SYSROOT") or subprocess.run(
        ["rustc", "--print", "sysroot"], capture_output=True, text=True, check=True, cwd="/").stdout.strip()
    src = Path(tmp) / "froid"
    shutil.copytree(FIXTURE, src)
    (src / "Cargo.toml.in").rename(src / "Cargo.toml")
    env = {"PATH": f"{sysroot}/bin:/usr/bin:/bin", "HOME": str(tmp), "CARGO_HOME": f"{tmp}/cargo",
           "CARGO_TARGET_DIR": f"{tmp}/target", "CARGO_NET_OFFLINE": "true", "LANG": "C.UTF-8"}
    subprocess.run([f"{sysroot}/bin/cargo", "build", "--release", "--offline", "--quiet"], cwd=src, env=env, check=True)
    return Path(tmp) / "target" / "release" / "froid"


def run_case(binary, case, work):
    work.mkdir(parents=True)
    for name, text in case["files"].items():
        (work / name).write_text(text, encoding="utf-8")
    args = [a.replace(DIR, str(work)) for a in case["args"]]
    r = subprocess.run([str(binary), *args], cwd=work, capture_output=True, timeout=120,
                       env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(work)})
    return r.returncode, r.stdout.replace(str(work).encode(), DIR.encode()), r.stderr.decode("utf-8", "replace")


STDERR_HAS = {  # fragments of the fixture's messages a port must keep (file and line; what is wrong)
    "bad-export": ["bad.log:4:", "bad temperature"], "missing-export": ["nowhere.log", "cannot read"],
    "bad-units": ["units.tsv:"], "bad-day": ["usage: froid"], "unknown-option": ["usage: froid"],
    "no-exports": ["usage: froid"], "check-bad": ["bad.log:4:"], "latest-usage": ["usage: froid"],
}


def main():
    cases = build_cases()
    out, store = [], {}
    with tempfile.TemporaryDirectory(prefix="revise-wrapper-rs-") as tmp:
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
            if case["kind"] == "digest" and rc == 0:
                want = model.digest_for(case, model.Variant())
                assert want.encode() == stdout, f"model and fixture differ on {case['name']}"
    digest_ok = [(c, e) for c, e in zip(cases, out) if c["kind"] == "digest" and e["rc"] == 0]
    for variant in model.VARIANTS:
        caught = [c["name"] for c, e in digest_ok
                  if model.digest_for(c, variant).encode() != base64.b64decode(e["stdout_b64"])]
        assert caught, f"no case tells {variant} apart"
        print(f"{variant.name}: caught by {', '.join(caught)}")
    doc = {"files": dict(sorted(store.items())), "cases": out}
    (HERE / "cases.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(out)} cases, {len(store)} distinct files written")


if __name__ == "__main__":
    main()
