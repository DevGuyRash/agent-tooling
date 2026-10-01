"""Regenerate hidden/cases.json: hidden tournaments and `td standings` command lines, with the expected exit
status and standard output from hidden/reference.py, which follows fixture/docs/standings.md, and command
lines of td's existing commands (check, players, card), with the results the fixture's own td gives.

    python3 hidden/make_cases.py                     # write cases.json
    python3 hidden/make_cases.py --cross-check TD    # also run a built td on every case and report differences
    python3 hidden/make_cases.py --fixture DIR       # rewrite the fixture's sample tournaments into DIR

The fixture's td is built here with the host's cargo, offline, from a copy of the fixture. A case's arguments
and expected standard output name its files as {dir}/NAME; the check replaces {dir} with the directory holding
that case's files, at the same absolute path in both roots it runs in. Every standings case is behavior the
spec states, so all are required except the few marked as measures; the existing-command cases guard what td
already did and count toward existing_tests_pass.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tournaments import swiss  # noqa: E402

WINTER = [(1, 2231, "Halvorsen, Ingrid"), (2, 2104, "Abara, Tobenna"), (3, 1987, "Okafor, Chidi"),
          (4, 1955, "Nguyễn, Thảo"), (5, 1890, "Brandt, Oskar"), (6, 1842, "Ødegård, Sigrid"),
          (7, 1777, "Castellanos, María José"), (8, 1610, "Li, Bo"), (9, 845, "Quinn, Aoife"),
          (10, 0, "Varga, Dénes"), (11, 0, "Price, Nora")]
CHAMP = [(1, 2105, "Lindqvist, Mia"), (2, 2040, "Kowalczyk, Ewa"), (3, 1987, "Okafor, Chidi"),
         (4, 1940, "Brandt, Oskar"), (5, 1862, "Šimić, Luka"), (6, 1848, "Achterberg, Joost"),
         (7, 1795, "Moreau, Élise"), (8, 1702, "Teo, Wen Jie"), (9, 1650, "Haddad, Rami"),
         (10, 1433, "Gallagher, Siobhán")]
EIGHT = [(1, 1990, "Achterberg, Joost"), (2, 1950, "Teo, Wen Jie"), (3, 1900, "Fenwick, Sam"),
         (4, 1850, "Moreau, Élise"), (5, 1800, "Haddad, Rami"), (6, 1750, "Gallagher, Siobhán"),
         (7, 1700, "Mensah, Kofi"), (8, 0, "Price, Nora")]
GIVEN = ["Ana", "Ben", "Cai", "Dara", "Eli", "Fen", "Gus", "Hana", "Ivo", "Jun", "Kit", "Lev", "Mo", "Nell", "Oto",
         "Pia", "Quy", "Rui", "Sol", "Tam"]
SURNAMES = ["Arendt", "Bianchi", "Chowdhury", "Dalca", "Eklund", "Ferreira", "Gruber", "Horvat", "Ivanova",
            "Jansen", "Kaur", "Lemaire", "Mbeki", "Novak", "O'Brien", "Petrov", "Quispe", "Rossi", "Sato", "Tanaka"]
OPEN = [(i + 1, 2300 - 23 * i if i % 9 else 0, f"{SURNAMES[i % 20]}, {GIVEN[(i * 7 + i // 20) % 20]}") for i in range(40)]


def quad():
    lines = ["event Quad", "rounds 3", ""] + [f"player {n} {r} {name}" for n, r, name in
                                              [(1, 1500, "Ash, Al"), (2, 1500, "Birch, Bea"), (3, 1500, "Cedar, Cy"), (4, 1500, "Dogwood, Di")]]
    for rnd, games in enumerate([[(1, 4), (2, 3)], [(4, 3), (1, 2)], [(2, 4), (3, 1)]], 1):
        lines += ["", f"round {rnd}"] + [f"{w} {b} 1/2" for w, b in games]
    return "\n".join(lines) + "\n"


TOURNAMENTS = {
    "winter-cup.trn": swiss("Winter Cup 2026", 6, WINTER, 6, seed=101,
                            special={2: [("half", 7)], 3: [("forfeit", 4)], 4: [("withdraw", 10)],
                                     5: [("double", 2)], 6: [("absent", 3)]}),
    "club-championship.trn": swiss("Club Championship 2026", 7, CHAMP, 5, seed=202,
                                   special={3: [("half", 9)], 4: [("forfeit", 1)]}, pending={5: [0, 3]}),
    "postponed.trn": swiss("Rapidplay, October", 5, EIGHT, 4, seed=303, pending={2: [2]}),
    "quad.trn": quad(),
    "fresh.trn": swiss("Newcomers' Cup", 4, EIGHT[:6], 1, seed=404, pending={1: [0, 1, 2]}),
    "unpaired.trn": swiss("Newcomers' Cup", 4, EIGHT[:6], 0, seed=404),
    "open.trn": swiss("Rookhaven Open 2026", 9, OPEN, 9, seed=505,
                      special={2: [("half", 17), ("half", 30)], 3: [("forfeit", 12), ("absent", 40)],
                               5: [("withdraw", 25), ("double", 3)], 7: [("forfeit", 8), ("half", 2)]}),
    "crlf.trn": swiss("Club Night (Windows laptop)", 3, EIGHT[:6], 3, seed=606, crlf=True,
                      header=["# saved on the club's Windows laptop", "", "# arbiter: M. Lindqvist"]),
}
BROKEN = """\
# Rookhaven Chess Club
event Thursday Blitz
rounds 3

player 1 1900 Able, Ann
player 2 1800 Baker, Bo
player 3 1700 Cole, Cy
player 4 1600 Dunn, Di

round 1
1 3 1-0
2 4 1/2

round 2
4 1 0-1
"""
TOURNAMENTS["unknown-player.trn"] = BROKEN + "13 2 1-0\n"  # line 16: unknown player 13
TOURNAMENTS["missing-player.trn"] = BROKEN + "\nround 3\n1 2 1/2\n3 4 1-0\n"  # 2 and 3 missing from round 2
TOURNAMENTS["bad-result.trn"] = BROKEN + "3 2 1-1\n"


def case(name, args, files, required=True, stderr_has=None, kind="standings"):
    return {"name": name, "kind": kind, "required": required, "args": ["standings", *args] if kind == "standings" else args,
            "files": {f: TOURNAMENTS[f] for f in files}, "stderr_has": stderr_has}


def existing(name, args, files, stderr_has=None):
    return case(name, args, files, stderr_has=stderr_has, kind="existing")


W, C, P = "{dir}/winter-cup.trn", "{dir}/club-championship.trn", "{dir}/postponed.trn"
CASES = [
    case("winter_default", [W], ["winter-cup.trn"]),
    case("winter_after_1", ["--after-round", "1", W], ["winter-cup.trn"]),
    case("winter_after_3", ["--after-round", "3", W], ["winter-cup.trn"]),
    case("winter_after_6", [W, "--after-round", "6"], ["winter-cup.trn"]),
    case("winter_sb_wins", ["--tiebreaks", "sb,wins", W], ["winter-cup.trn"]),
    case("winter_no_tiebreaks", ["--tiebreaks", "none", W], ["winter-cup.trn"]),
    case("winter_options_after_file", [W, "--tiebreaks", "wins,bh1", "--after-round", "5"], ["winter-cup.trn"]),
    case("winter_bh_only", ["--tiebreaks", "bh", W], ["winter-cup.trn"]),
    case("championship_default", [C], ["club-championship.trn"]),
    case("championship_after_2", ["--after-round", "2", C], ["club-championship.trn"]),
    case("championship_after_unfinished", ["--after-round", "5", C], ["club-championship.trn"],
         stderr_has=["td: ", "round 5 is not finished"]),
    case("championship_after_unpaired", ["--after-round", "6", C], ["club-championship.trn"],
         stderr_has=["td: ", "round 6 has not been paired"]),
    case("championship_after_beyond_planned", ["--after-round", "9", C], ["club-championship.trn"],
         stderr_has=["td: ", "round 9 has not been paired"]),
    case("postponed_default", [P], ["postponed.trn"]),
    case("postponed_after_4", ["--after-round", "4", P], ["postponed.trn"], stderr_has=["td: ", "round 2 is not finished"]),
    case("postponed_after_1", ["--after-round", "1", "--tiebreaks", "wins,sb,bh,bh1", P], ["postponed.trn"]),
    case("quad_all_drawn", ["{dir}/quad.trn"], ["quad.trn"]),
    case("quad_no_tiebreaks_after_2", ["{dir}/quad.trn", "--tiebreaks", "none", "--after-round", "2"], ["quad.trn"]),
    case("fresh_no_finished_round", ["{dir}/fresh.trn"], ["fresh.trn"], stderr_has=["td: ", "no finished rounds"]),
    case("fresh_after_1", ["--after-round", "1", "{dir}/fresh.trn"], ["fresh.trn"], stderr_has=["td: ", "round 1 is not finished"]),
    case("unpaired_no_finished_round", ["{dir}/unpaired.trn"], ["unpaired.trn"], stderr_has=["td: ", "no finished rounds"]),
    case("unpaired_after_1", ["--after-round", "1", "{dir}/unpaired.trn"], ["unpaired.trn"],
         stderr_has=["td: ", "round 1 has not been paired"]),
    case("open_default", ["{dir}/open.trn"], ["open.trn"]),
    case("open_after_7_sb", ["--after-round", "7", "--tiebreaks", "sb", "{dir}/open.trn"], ["open.trn"]),
    case("open_after_4_bh_bh1", ["--tiebreaks", "bh,bh1", "--after-round", "4", "{dir}/open.trn"], ["open.trn"]),
    case("crlf_file", ["{dir}/crlf.trn"], ["crlf.trn"]),
    case("invalid_unknown_player", ["{dir}/unknown-player.trn"], ["unknown-player.trn"], stderr_has=["td: ", ": unknown player 13"]),
    case("invalid_missing_player", ["{dir}/missing-player.trn"], ["missing-player.trn"], stderr_has=["td: ", "is missing from round"]),
    case("invalid_result", ["{dir}/bad-result.trn"], ["bad-result.trn"], stderr_has=["td: ", "unknown result \"1-1\""]),
    case("missing_file", ["{dir}/no-such-file.trn"], [], stderr_has="td: "),
    case("usage_unknown_tiebreak", ["--tiebreaks", "bh,median", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_repeated_tiebreak", ["--tiebreaks", "sb,bh,sb", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_none_with_others", ["--tiebreaks", "none,bh", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_empty_tiebreaks", ["--tiebreaks", "", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_after_zero", ["--after-round", "0", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_after_word", ["--after-round", "two", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_after_negative", ["--after-round", "-1", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_after_fraction", ["--after-round", "2.5", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_missing_value", [W, "--after-round"], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_no_file", [], [], stderr_has="td: "),
    case("usage_two_files", [W, C], ["winter-cup.trn", "club-championship.trn"], stderr_has="td: "),
    case("usage_unknown_option", ["--json", W], ["winter-cup.trn"], stderr_has="td: "),
    case("usage_option_twice", ["--after-round", "2", "--after-round", "3", W], ["winter-cup.trn"], stderr_has="td: "),
    # Measures: forms the spec does not settle.
    case("m_after_leading_zero", ["--after-round", "03", W], ["winter-cup.trn"], required=False),
    case("m_tiebreaks_upper_case", ["--tiebreaks", "SB", W], ["winter-cup.trn"], required=False),
    case("m_space_in_tiebreaks", ["--tiebreaks", "sb, wins", W], ["winter-cup.trn"], required=False),
    # td's existing commands, as the fixture's td answers them.
    existing("existing_check_finished", ["check", W], ["winter-cup.trn"]),
    existing("existing_check_pending", ["check", C], ["club-championship.trn"]),
    existing("existing_check_postponed", ["check", P], ["postponed.trn"]),
    existing("existing_check_crlf", ["check", "{dir}/crlf.trn"], ["crlf.trn"]),
    existing("existing_check_invalid", ["check", "{dir}/unknown-player.trn"], ["unknown-player.trn"],
             stderr_has=["td: ", ": unknown player 13"]),
    existing("existing_players", ["players", "{dir}/open.trn"], ["open.trn"]),
    existing("existing_players_by_name", ["players", "--by", "name", W], ["winter-cup.trn"]),
    existing("existing_players_by_rating", ["players", W, "--by", "rating"], ["winter-cup.trn"]),
    existing("existing_players_bad_by", ["players", "--by", "elo", W], ["winter-cup.trn"], stderr_has="td: "),
    existing("existing_card_forfeit", ["card", W, "4"], ["winter-cup.trn"]),
    existing("existing_card_withdrawn", ["card", W, "10"], ["winter-cup.trn"]),
    existing("existing_card_pending", ["card", C, "4"], ["club-championship.trn"]),
    existing("existing_card_no_player", ["card", W, "12"], ["winter-cup.trn"], stderr_has=["td: ", "no player 12"]),
    existing("existing_card_bad_number", ["card", W, "x"], ["winter-cup.trn"], stderr_has="td: "),
]


def run(argv, files):
    """(exit status, standard output with the files' directory written as {dir}, standard error)."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in files.items():
            (Path(tmp) / name).write_bytes(text.encode("utf-8"))
        args = [a.replace("{dir}", tmp) for a in argv]
        r = subprocess.run(args, cwd=tmp, capture_output=True, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    return r.returncode, r.stdout.replace(tmp.encode(), b"{dir}"), r.stderr.decode("utf-8", "replace")


def build_fixture_td(work):
    """The fixture's own td, built offline with the host's cargo from a copy of the fixture under work."""
    src = Path(work) / "fixture"
    shutil.copytree(HERE.parent / "fixture", src, ignore=shutil.ignore_patterns("target"))
    for manifest in src.rglob("Cargo.toml.in"):
        manifest.rename(manifest.with_suffix(""))
    cargo = shutil.which("cargo") or sys.exit("cargo is needed to build the fixture's td")
    subprocess.run([cargo, "build", "--release", "--offline", "--quiet", "-p", "td"], cwd=src, check=True,
                   env=dict(os.environ, CARGO_TARGET_DIR=str(Path(work) / "target")))
    return str(Path(work) / "target" / "release" / "td")


def expected(c, fixture_td):
    if c["kind"] == "existing":
        return run([fixture_td, *c["args"]], c["files"])
    return run([sys.executable, str(HERE / "reference.py"), *c["args"]], c["files"])


def main(argv):
    if argv[:1] == ["--fixture"]:
        write_fixture(Path(argv[1]))
        return 0
    cross = argv[1] if argv[:1] == ["--cross-check"] else None
    out, problems = [], []
    with tempfile.TemporaryDirectory() as work:
        fixture_td = build_fixture_td(work)
        for c in CASES:
            rc, stdout, stderr = expected(c, fixture_td)
            if rc != 0 and stdout:
                raise SystemExit(f"{c['name']}: the expected result has output on error")
            wanted = c["stderr_has"] if rc != 0 else None
            for w in ([wanted] if isinstance(wanted, str) else wanted or []):
                if w not in stderr:
                    raise SystemExit(f"{c['name']}: the expected stderr lacks {w!r}: {stderr!r}")
            if cross:
                got = run([cross, *c["args"]], c["files"])
                if got[0] != rc or got[1] != stdout or any(w not in got[2] for w in ([wanted] if isinstance(wanted, str) else wanted or [])):
                    problems.append(f"{c['name']}: td gave {got[0]} {got[1][:80]!r} {got[2][:120]!r}, expected {rc} {stdout[:80]!r} {stderr[:120]!r}")
            out.append({"name": c["name"], "kind": c["kind"], "required": c["required"], "args": c["args"],
                        "files_b64": {k: base64.b64encode(v.encode("utf-8")).decode() for k, v in c["files"].items()},
                        "rc": rc, "stdout_b64": base64.b64encode(stdout).decode(), "stderr_has": wanted})
    (HERE / "cases.json").write_text(json.dumps({"program": "td", "cases": out}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(out)} cases written to {HERE / 'cases.json'}")
    for p in problems:
        print(p)
    return 1 if problems else 0


def write_fixture(directory):
    spring = [(1, 2105, "Lindqvist, Mia"), (2, 1987, "Okafor, Chidi"), (3, 1940, "Brandt, Oskar"),
              (4, 1862, "Šimić, Luka"), (5, 1795, "Moreau, Élise"), (6, 1710, "Fenwick, Sam"), (7, 1650, "Haddad, Rami"),
              (8, 0, "Price, Nora")]
    summer = [(1, 1987, "Okafor, Chidi"), (2, 1940, "Brandt, Oskar"), (3, 1921, "Kowalczyk, Ewa"),
              (4, 1848, "Achterberg, Joost"), (5, 1795, "Moreau, Élise"), (6, 1702, "Teo, Wen Jie"),
              (7, 1650, "Haddad, Rami"), (8, 1433, "Gallagher, Siobhán"), (9, 0, "Mensah, Kofi")]
    autumn = [(1, 2105, "Lindqvist, Mia"), (2, 1987, "Okafor, Chidi"), (3, 1940, "Brandt, Oskar"),
              (4, 1921, "Kowalczyk, Ewa"), (5, 1862, "Šimić, Luka"), (6, 1848, "Achterberg, Joost"),
              (7, 1795, "Moreau, Élise"), (8, 1710, "Fenwick, Sam"), (9, 1702, "Teo, Wen Jie"), (10, 1650, "Haddad, Rami"),
              (11, 1433, "Gallagher, Siobhán"), (12, 0, "Price, Nora")]
    files = {
        "spring-rapid-2026.trn": swiss("Spring Rapid 2026", 5, spring, 5, seed=7,
                                       special={2: [("half", 6)], 4: [("forfeit", 7)]}),
        "summer-blitz-2026.trn": swiss("Summer Blitz 2026", 7, summer, 7, seed=11,
                                       special={5: [("withdraw", 9)], 3: [("double", 4)]}),
        "autumn-league-2026.trn": swiss("Autumn League 2026", 7, autumn, 3, seed=23,
                                        special={2: [("half", 11), ("absent", 12)]}, pending={3: [1, 4]}),
    }
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    print(f"{len(files)} tournaments written to {directory}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
