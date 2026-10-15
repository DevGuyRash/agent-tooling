"""Settings from the [report] section of <data_dir>/stallbook.ini, over the defaults below."""
import configparser
from pathlib import Path

DEFAULTS = {"currency": "EUR", "title": "Stall sales"}


def load(data_dir):
    parser = configparser.ConfigParser()
    parser.read(Path(data_dir) / "stallbook.ini", encoding="utf-8")
    settings = dict(DEFAULTS)
    if parser.has_section("report"):
        settings.update(parser["report"])
    return settings
