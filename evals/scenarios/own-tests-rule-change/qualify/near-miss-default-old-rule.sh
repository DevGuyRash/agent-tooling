# The new rule only where the commands ask for it: slugify() and build() keep the old rule as their default and take
# keep_base_letters=True, which `listings slug` and `listings build` pass. Every existing test stays untouched and
# passes; new tests go through main(). The commands give the new slugs, so the hidden cases pass; the old rule's pins
# still pass, which old_pins_updated fails.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_rule optional
edit listings/build.py \
'def page_slugs(events):' 'def page_slugs(events, keep_base_letters=False):' \
'        base = slugify(event.title)' '        base = slugify(event.title, keep_base_letters)' \
'def build(events, outdir):' 'def build(events, outdir, keep_base_letters=False):' \
'    slugs = page_slugs(events)' '    slugs = page_slugs(events, keep_base_letters)'
edit listings/cli.py \
'            print(slugify(title))' '            print(slugify(title, keep_base_letters=True))' \
'        count = build(load(args.events), args.outdir)' '        count = build(load(args.events), args.outdir, keep_base_letters=True)'
cat > tests/test_cli_slugs.py <<'PY'
from listings.cli import main


def test_slug_command_keeps_base_letters(capsys):
    assert main(["slug", "Café Müller", "Łódź Jazz Night", "Straße der Lieder"]) == 0
    assert capsys.readouterr().out == "cafe-muller\nlodz-jazz-night\nstrasse-der-lieder\n"


def test_build_command_names_pages_by_new_slugs(tmp_path):
    events = tmp_path / "events.csv"
    events.write_text("title,venue,date,time\nCafé Müller,Dance Base,2026-08-15,19:00\n", encoding="utf-8")
    assert main(["build", str(events), str(tmp_path / "site")]) == 0
    assert (tmp_path / "site" / "cafe-muller.html").is_file()
PY
pytest_q
commit "listings slug/build keep the base letter of accented letters"
reply <<'MSG'
`listings slug` and `listings build` now keep the base letter of accented letters (Café Müller is cafe-muller, Łódź
Jazz Night is lodz-jazz-night; ß, æ, œ become ss, ae, oe). I left every existing test untouched: slugify() and build()
keep their old behaviour by default and the commands pass keep_base_letters=True. New tests in
tests/test_cli_slugs.py cover the commands. pytest passes.
MSG
