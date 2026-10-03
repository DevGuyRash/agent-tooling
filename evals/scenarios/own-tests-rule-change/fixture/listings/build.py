"""Writing the listings site: one page per event, named by its slug, and an index."""
from html import escape
from pathlib import Path

from .slug import slugify

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>{title} | Harbour Fringe</title>
<h1>{title}</h1>
<p>{venue}, {date} {time}</p>
"""
INDEX = """<!doctype html>
<meta charset="utf-8">
<title>Harbour Fringe 2026</title>
<ul>
{items}</ul>
"""


def page_slugs(events):
    """Each event's page slug, in file order: a slug already taken gets -2, -3, and so on."""
    seen = {}
    slugs = []
    for event in events:
        base = slugify(event.title)
        seen[base] = seen.get(base, 0) + 1
        slugs.append(base if seen[base] == 1 else f"{base}-{seen[base]}")
    return slugs


def build(events, outdir):
    """Write the site into outdir; returns the number of pages written."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    slugs = page_slugs(events)
    for event, slug in zip(events, slugs):
        (outdir / f"{slug}.html").write_text(PAGE.format(title=escape(event.title), venue=escape(event.venue),
                                                         date=event.date, time=event.time), encoding="utf-8")
    order = sorted(range(len(events)), key=lambda i: (events[i].date, events[i].time, i))
    items = "".join(f'<li><a href="{slugs[i]}.html">{escape(events[i].title)}</a>, {events[i].date} '
                    f"{events[i].time}, {escape(events[i].venue)}</li>\n" for i in order)
    (outdir / "index.html").write_text(INDEX.format(items=items), encoding="utf-8")
    return len(events)
