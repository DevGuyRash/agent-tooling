from pathlib import Path

import pytest

from shiftboard.board import render_week
from shiftboard.cli import main
from shiftboard.roster import load

EXAMPLES = Path(__file__).parent.parent / "docs" / "examples"


def test_doc_example(capsys):
    assert main(["week", str(EXAMPLES / "roster-sample.csv"), "2026-W38"]) == 0
    assert capsys.readouterr().out == (EXAMPLES / "week-2026-W38.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("week", ["2026-38", "2026-W54", "2025-W53", "2026-W00"])
def test_bad_weeks(week, capsys):
    assert main(["week", str(EXAMPLES / "roster-sample.csv"), week]) == 2
    assert capsys.readouterr().err == f"shiftboard: bad week '{week}'\n"


def test_wide_names_line_up(tmp_path):
    path = tmp_path / "r.csv"
    path.write_text("date,start,end,station,volunteer\n"
                    "2026-09-14,09:00,12:00,Prep,张伟\n"
                    "2026-09-14,09:00,12:00,Serving,Amara Okafor\n", encoding="utf-8")
    lines = render_week(load(path), "2026-W38").splitlines()
    assert lines[2] == "Mon 14  09:00-12:00  张伟          Prep"
    assert lines[3] == "Mon 14  09:00-12:00  Amara Okafor  Serving"


def test_empty_week():
    assert render_week([], "2026-W40") == "No shifts in 2026-W40."
