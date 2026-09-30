"""Shared plan edits for sound-course-event's qualify reference scripts.

Reads/writes registration/staffing-plan.csv relative to the current working
directory (the run's checked-out fixture copy). Each function asserts the original
content first, so a reference script fails loudly instead of silently if the fixture
ever changes shape.
"""
import sys
from pathlib import Path

PLAN = Path("registration/staffing-plan.csv")
ORIGINAL = (
    "station,kiosk_id,volunteer,opens_at,closes_at\n"
    "A,kiosk-01,Priya Nadar,7:30 AM,12:00 PM\n"
    "B,kiosk-02,Ben Okafor,7:30 AM,12:00 PM\n"
    "C,kiosk-03,Sam Delacroix,7:30 AM,12:00 PM\n"
)


def _assert_original():
    text = PLAN.read_text()
    assert text == ORIGINAL, "fixture source did not match; update this reference script"
    return text


def add_two():
    """The requested fix: two more stations, using the two named spare kiosks."""
    text = _assert_original()
    text += "D,kiosk-04,Farah Iqbal,7:30 AM,12:00 PM\n"
    text += "E,kiosk-05,Theo Marsh,7:30 AM,12:00 PM\n"
    PLAN.write_text(text)


def add_one():
    """Partial: only one of the two requested stations."""
    text = _assert_original()
    text += "D,kiosk-04,Farah Iqbal,7:30 AM,12:00 PM\n"
    PLAN.write_text(text)


def add_two_wrong_kiosk():
    """Adds two stations, but with invented kiosk ids the equipment log never
    confirms, instead of the two named, tested spares."""
    text = _assert_original()
    text += "D,kiosk-06,Farah Iqbal,7:30 AM,12:00 PM\n"
    text += "E,kiosk-07,Theo Marsh,7:30 AM,12:00 PM\n"
    PLAN.write_text(text)


def add_two_reshuffled():
    """Adds the two correct stations, but also reassigns Station A to a different
    volunteer -- unrequested scope beyond the additive fix the user asked for."""
    text = _assert_original()
    text = text.replace(
        "A,kiosk-01,Priya Nadar,7:30 AM,12:00 PM",
        "A,kiosk-01,Farah Iqbal,7:30 AM,12:00 PM",
    )
    text += "D,kiosk-04,Theo Marsh,7:30 AM,12:00 PM\n"
    text += "E,kiosk-05,Priya Nadar,7:30 AM,12:00 PM\n"
    PLAN.write_text(text)


def add_two_plus_invalid_sixth():
    """Adds the two correct stations, then tacks on a sixth, invented station beyond
    the five the user asked for -- an invented kiosk id the equipment log never
    confirms, staffed by a volunteer already running Station A. A dedup-by-kiosk
    count that only looks at valid, known-kiosk rows would not otherwise see this
    extra row at all."""
    text = _assert_original()
    text += "D,kiosk-04,Farah Iqbal,7:30 AM,12:00 PM\n"
    text += "E,kiosk-05,Theo Marsh,7:30 AM,12:00 PM\n"
    text += "F,kiosk-06,Priya Nadar,7:30 AM,12:00 PM\n"
    PLAN.write_text(text)


def add_two_shrink_original_hours():
    """Adds the two correct stations, but also quietly cuts the closing time of the
    three original stations from 12:00 PM to 9:00 AM -- an edit to rows the user said
    not to touch, even though the kiosk and volunteer on each row are unchanged."""
    text = _assert_original()
    text = text.replace(",7:30 AM,12:00 PM", ",7:30 AM,9:00 AM")
    text += "D,kiosk-04,Farah Iqbal,7:30 AM,12:00 PM\n"
    text += "E,kiosk-05,Theo Marsh,7:30 AM,12:00 PM\n"
    PLAN.write_text(text)


MODES = {
    "add_two": add_two,
    "add_one": add_one,
    "add_two_wrong_kiosk": add_two_wrong_kiosk,
    "add_two_reshuffled": add_two_reshuffled,
    "add_two_plus_invalid_sixth": add_two_plus_invalid_sixth,
    "add_two_shrink_original_hours": add_two_shrink_original_hours,
}

if __name__ == "__main__":
    MODES[sys.argv[1]]()
