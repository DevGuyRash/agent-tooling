"""Writes cases.json: the hidden exports and the commands the check runs on them. Expected output is not
stored; check.py computes it with reference.py under the documented rule and under each edit.

Three kinds of case. policy: inputs on which the fixture's three copies of the rule, each with the request
applied, all agree (no second permits, no band C vehicles, no vehicle exactly on 100, 120, 150, 185, 225, or
255 g/km), so they show the request: band G over 255 g/km and the 45.00 diesel surcharge. drift: inputs on which
those copies disagree, for every command, so they show whether the drift was resolved to
docs/permit-charges.md. existing: behavior the request does not touch (an export with a byte-order mark and
Windows line endings, columns in another order and values in any case, refusals, a month with no renewals,
bad command lines). check.py verifies the policy/drift split and that every edit it makes changes some output
of every command before each run.

Run from this directory: python3 make_cases.py"""
import json
from pathlib import Path

HEADER = "permit_id,address,vrm,co2,fuel,household_permit,expires\n"


def export(rows, newline="\n"):
    return (HEADER + "".join(",".join(map(str, r)) + "\n" for r in rows)).replace("\n", newline)


# (permit, address, registration, g/km, fuel, household permit, expires)
POLICY = [
    ("FV-20101", "2 Abbey Mews", "AA01 AAA", 0, "electric", 1, "2027-04-03"),
    ("FV-20102", "5 Brook Street", "AB02 BBB", 87, "petrol", 1, "2027-04-03"),
    ("FV-20103", "11 Chapel Lane", "AC03 CCC", 112, "hybrid", 1, "2027-04-11"),
    ("FV-20104", "19 Dene Road", "AD04 DDD", 171, "petrol", 1, "2027-04-17"),
    ("FV-20105", "23 Elm Grove", "AE05 EEE", 183, "diesel", 1, "2027-04-17"),
    ("FV-20106", "30 Ferry Lane", "AF06 FFF", 199, "petrol", 1, "2027-04-22"),
    ("FV-20107", "4 Glebe Close", "AG07 GGG", 240, "diesel", 1, "2027-04-28"),
    ("FV-20109", "12 Ivy Terrace", "AJ09 JJJ", 256, "petrol", 1, "2027-05-02"),
    ("FV-20110", "16 Jubilee Way", "AK10 KKK", 258, "diesel", 1, "2027-05-09"),
    ("FV-20111", "20 Kiln Row", "AL11 LLL", 260, "hybrid", 1, "2027-05-15"),
    ("FV-20112", "24 Lark Rise", "AM12 MMM", 261, "petrol", 1, "2027-05-21"),
    ("FV-20114", "32 North Road", "AP14 PPP", 219, "diesel", 1, "2027-05-27"),
    ("FV-20113", "28 Mill Street", "AN13 NNN", 304, "diesel", 1, "2027-05-27"),
    ("FV-20115", "36 Orchard Way", "AR15 RRR", 101, "petrol", 1, "2027-06-04"),
    ("FV-20116", "40 Priory Walk", "AS16 SSS", 186, "hybrid", 1, "2027-05-11"),
    ("FV-20117", "44 Quay Street", "AT17 TTT", 226, "petrol", 1, "2027-04-08"),
]
DRIFT = [
    ("FV-20201", "2 Abbey Mews", "BA01 AAA", 95, "petrol", 2, "2027-04-03"),
    ("FV-20202", "7 Brook Street", "BB02 BBB", 135, "hybrid", 1, "2027-04-05"),
    ("FV-20203", "9 Canal Side", "BC03 CCC", 150, "diesel", 1, "2027-04-09"),
    ("FV-20204", "13 Dock Road", "BD04 DDD", 100, "petrol", 1, "2027-04-12"),
    ("FV-20205", "17 Eel Pie Lane", "BE05 EEE", 120, "hybrid", 1, "2027-04-12"),
    ("FV-20206", "21 Fen Lane", "BF06 FFF", 185, "diesel", 2, "2027-04-20"),
    ("FV-20207", "25 Gate Street", "BG07 GGG", 225, "petrol", 1, "2027-04-26"),
    ("FV-20208", "29 Hythe Road", "BH08 HHH", 121, "petrol", 2, "2027-05-03"),
    ("FV-20209", "33 Inkerman Street", "BJ09 JJJ", 270, "diesel", 3, "2027-05-08"),
    ("FV-20210", "37 Jasmine Court", "BK10 KKK", 160, "petrol", 2, "2027-05-14"),
    ("FV-20211", "8 Hall Gardens", "BL11 LLL", 255, "petrol", 1, "2027-04-30"),
]

FILES = {
    "policy.csv": export(POLICY),
    "drift.csv": export(DRIFT),
    # Existing behavior: a byte-order mark and Windows line endings, as the permit system writes them, with
    # rows out of order.
    "bom-crlf.csv": "\ufeff" + export([
        ("FV-20305", "6 Rope Walk", "CE05 EEE", 199, "hybrid", 1, "2027-04-21"),
        ("FV-20301", "3 Rope Walk", "CA01 AAA", 64, "electric", 1, "2027-04-21"),
        ("FV-20303", "5 Rope Walk", "CC03 CCC", 177, "petrol", 1, "2027-04-02"),
        ("FV-20302", "4 Rope Walk", "CB02 BBB", 110, "petrol", 1, "2027-05-02"),
    ], "\r\n"),
    # Columns in another order, values padded, fuel and registration in any case.
    "reordered.csv": ("expires,fuel,co2,household_permit,vrm,address,permit_id\n"
                      " 2027-04-14 , Petrol ,172, 1 ,dk61 vbn, 10 Salt Lane ,FV-20401\n"
                      "2027-04-15,HYBRID, 115 ,1,ef62 wsx,12 Salt Lane,FV-20402\n"),
    "no-column.csv": "permit_id,address,vrm,co2,fuel,expires\nFV-1,1 Mill Lane,AB12 CDE,140,petrol,2027-04-01\n",
    "bad-co2.csv": export([("FV-20501", "1 Mill Lane", "AB12 CDE", "lots", "petrol", 1, "2027-04-01")]),
    "negative-co2.csv": export([("FV-20502", "1 Mill Lane", "AB12 CDE", -4, "petrol", 1, "2027-04-01")]),
    "bad-fuel.csv": export([("FV-20503", "1 Mill Lane", "AB12 CDE", 140, "lpg", 1, "2027-04-01")]),
    "bad-household.csv": export([("FV-20504", "1 Mill Lane", "AB12 CDE", 140, "petrol", 0, "2027-04-01")]),
    "bad-date.csv": export([("FV-20505", "1 Mill Lane", "AB12 CDE", 140, "petrol", 1, "2027-06-31")]),
    "empty.csv": "",
}


def case(name, kind, *args):
    return {"name": name, "kind": kind, "args": list(args)}


def quotes(kind, specs):
    out = []
    for co2, fuel, second in specs:
        args = ["quote", "-co2", str(co2), "-fuel", fuel] + (["-second"] if second else [])
        out.append(case(f"{kind}:quote:{co2}-{fuel}{'-second' if second else ''}", kind, *args))
    return out


CASES = (
    quotes("policy", [(0, "electric", False), (87, "petrol", False), (101, "petrol", False), (112, "hybrid", False),
                      (171, "petrol", False), (183, "diesel", False), (186, "petrol", False), (199, "petrol", False),
                      (226, "petrol", False), (240, "diesel", False), (256, "petrol", False),
                      (258, "diesel", False), (260, "hybrid", False), (261, "petrol", False), (304, "diesel", False)])
    + [case("policy:renewals:2027-04", "policy", "renewals", "-month", "2027-04", "{policy.csv}"),
       case("policy:renewals:2027-05", "policy", "renewals", "-month", "2027-05", "{policy.csv}"),
       case("policy:forecast", "policy", "forecast", "{policy.csv}")]
    + quotes("drift", [(95, "petrol", True), (160, "diesel", True), (270, "petrol", True), (135, "hybrid", False),
                       (121, "petrol", False), (150, "petrol", False), (100, "petrol", False), (120, "diesel", False),
                       (185, "petrol", False), (225, "diesel", False), (255, "petrol", False)])
    + [case("drift:renewals:2027-04", "drift", "renewals", "-month", "2027-04", "{drift.csv}"),
       case("drift:renewals:2027-05", "drift", "renewals", "-month", "2027-05", "{drift.csv}"),
       case("drift:forecast", "drift", "forecast", "{drift.csv}")]
    + [
        case("existing:renewals:bom-crlf", "existing", "renewals", "-month", "2027-04", "{bom-crlf.csv}"),
        case("existing:renewals:reordered", "existing", "renewals", "-month", "2027-04", "{reordered.csv}"),
        case("existing:renewals:none-due", "existing", "renewals", "-month", "2027-08", "{policy.csv}"),
        case("existing:quote:fuel-case", "existing", "quote", "-co2", "171", "-fuel", "Hybrid"),
        case("existing:quote:default-fuel", "existing", "quote", "-co2", "64"),
        case("existing:renewals:missing-file", "existing", "renewals", "-month", "2027-04", "{missing.csv}"),
        case("existing:forecast:missing-file", "existing", "forecast", "{missing.csv}"),
        case("existing:renewals:no-column", "existing", "renewals", "-month", "2027-04", "{no-column.csv}"),
        case("existing:renewals:bad-co2", "existing", "renewals", "-month", "2027-04", "{bad-co2.csv}"),
        case("existing:renewals:negative-co2", "existing", "renewals", "-month", "2027-04", "{negative-co2.csv}"),
        case("existing:forecast:bad-fuel", "existing", "forecast", "{bad-fuel.csv}"),
        case("existing:forecast:bad-household", "existing", "forecast", "{bad-household.csv}"),
        case("existing:renewals:bad-date", "existing", "renewals", "-month", "2027-04", "{bad-date.csv}"),
        case("existing:forecast:empty", "existing", "forecast", "{empty.csv}"),
        case("existing:usage:none", "existing"),
        case("existing:usage:unknown-command", "existing", "refund", "{policy.csv}"),
        case("existing:usage:quote-no-co2", "existing", "quote"),
        case("existing:usage:quote-negative", "existing", "quote", "-co2", "-5"),
        case("existing:usage:quote-not-number", "existing", "quote", "-co2", "lots"),
        case("existing:usage:quote-fuel", "existing", "quote", "-co2", "120", "-fuel", "lpg"),
        case("existing:usage:quote-extra-argument", "existing", "quote", "-co2", "120", "now"),
        case("existing:usage:renewals-no-month", "existing", "renewals", "{policy.csv}"),
        case("existing:usage:renewals-bad-month", "existing", "renewals", "-month", "April", "{policy.csv}"),
        case("existing:usage:forecast-none", "existing", "forecast"),
        case("existing:usage:forecast-two", "existing", "forecast", "{policy.csv}", "{drift.csv}"),
    ]
)

if __name__ == "__main__":
    doc = {"note": "Inputs only: expected output comes from reference.py at check time. Arguments {name} are the "
                   "files below, written to the case directory; a name not listed is a missing file.",
           "files": FILES, "cases": CASES}
    Path(__file__).with_name("cases.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
