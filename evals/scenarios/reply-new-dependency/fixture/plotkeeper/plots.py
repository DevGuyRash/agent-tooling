"""Reading the society's plot register (data/plots.csv)."""
import datetime
import re
from dataclasses import dataclass

HEADER = "plot,size_m2,kind,holder,start,concession,water"
KINDS = ("full", "half", "bed", "community")
WATER_NAMES = {"": "-", "Y": "standpipe", "T": "trough"}

_PLOT_ID = re.compile(r"[A-Z][0-9]{1,3}")
_SIZE = re.compile(r"[1-9][0-9]*")
_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")


class PlotsError(Exception):
    """A problem with the register: "FILE line N: what is wrong", or "cannot read FILE"."""


@dataclass(frozen=True)
class Plot:
    plot: str
    size_m2: int
    kind: str
    holder: str  # "" when the plot is vacant
    start: datetime.date | None  # when the holder took the plot
    concession: bool
    water: str  # "", "Y" (own standpipe), or "T" (shares a trough)

    @property
    def site(self):
        return self.plot[0]

    @property
    def number(self):
        return int(self.plot[1:])

    @property
    def vacant(self):
        return not self.holder


def plot_order(plot):
    """Sort key: site letter, then plot number as a number (A2 before A10)."""
    return (plot.site, plot.number)


def _date(text):
    m = _DATE.fullmatch(text)
    if not m:
        return None
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def read_plots(path):
    """The plots in the register at `path`, in file order. Raises PlotsError."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        raise PlotsError(f"cannot read {path}") from None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    lines = [line[:-1] if line.endswith("\r") else line for line in lines]

    def fail(n, msg):
        raise PlotsError(f"{path} line {n}: {msg}")

    if not lines or lines[0] != HEADER:
        fail(1, f"expected header {HEADER}")
    plots, seen = [], set()
    for n, line in enumerate(lines[1:], start=2):
        if not line.strip(" \t"):
            continue
        fields = [f.strip(" \t") for f in line.split(",")]
        if len(fields) != 7:
            fail(n, f"expected 7 fields, found {len(fields)}")
        plot, size, kind, holder, start, concession, water = fields
        if not _PLOT_ID.fullmatch(plot):
            fail(n, f'bad plot id "{plot}"')
        if plot in seen:
            fail(n, f"plot {plot} listed twice")
        seen.add(plot)
        if not _SIZE.fullmatch(size):
            fail(n, f'bad size "{size}"')
        if kind not in KINDS:
            fail(n, f'unknown kind "{kind}"')
        date = None
        if holder or start:
            date = _date(start)
            if date is None:
                fail(n, f'bad start date "{start}"')
        if concession not in ("", "Y"):
            fail(n, f'bad concession flag "{concession}"')
        if water not in ("", "Y", "T"):
            fail(n, f'bad water flag "{water}"')
        plots.append(Plot(plot, int(size), kind, holder, date, concession == "Y", water))
    return plots
