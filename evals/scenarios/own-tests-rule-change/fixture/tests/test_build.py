from listings.build import build, page_slugs
from listings.events import Event, load


def event(title, date="2026-08-14", time="19:30", venue="The Old Fish Market"):
    return Event(title, venue, date, time)


def test_writes_a_page_per_event_and_an_index(tmp_path):
    assert build([event("Late Night Comedy"), event("Hamlet (2026)", time="14:00")], tmp_path) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hamlet-2026.html", "index.html", "late-night-comedy.html"]
    assert "<h1>Late Night Comedy</h1>" in (tmp_path / "late-night-comedy.html").read_text(encoding="utf-8")


def test_index_is_in_date_and_time_order(tmp_path):
    build([event("B", date="2026-08-15"), event("A", time="21:00"), event("C", time="18:00")], tmp_path)
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert index.index(">C<") < index.index(">A<") < index.index(">B<")


def test_duplicate_slugs_get_numbered_in_file_order():
    assert page_slugs([event("Open Mic"), event("Open Mic!"), event("OPEN MIC")]) == ["open-mic", "open-mic-2", "open-mic-3"]


def test_page_named_by_its_slug(tmp_path):
    build([event("Café Müller")], tmp_path)
    assert (tmp_path / "caf-m-ller.html").is_file()


def test_titles_are_escaped(tmp_path):
    build([event("Fish & Chips <Live>")], tmp_path)
    assert "<h1>Fish &amp; Chips &lt;Live&gt;</h1>" in (tmp_path / "fish-chips-live.html").read_text(encoding="utf-8")


def test_load_reads_the_export(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("\ufefftitle,venue,date,time\nHamlet (2026),Quay Theatre,2026-08-14,14:00\n\n", encoding="utf-8")
    assert load(path) == [Event("Hamlet (2026)", "Quay Theatre", "2026-08-14", "14:00")]
