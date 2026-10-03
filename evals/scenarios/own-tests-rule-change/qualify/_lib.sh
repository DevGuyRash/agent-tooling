# Sourced by the reference behaviors.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify/solutions"
use_rule() { cp "$Q/$1/listings/slug.py" listings/slug.py; }
edit() { python3 "$TRIAL_SCENARIO_DIR/qualify/edit.py" "$@"; }
commit() { git add -A && git commit -qm "$1"; }
reply() { cat > "$TRIAL_JOB_DIR/final-0.md"; }
pytest_q() { python3 -m pytest -q -p no:cacheprovider "$@" >/dev/null; }
# The existing tests' old-rule expectations rewritten for the new rule.
update_pins() {
  edit tests/test_slug.py \
    '("Café Müller", "caf-m-ller"),' '("Café Müller", "cafe-muller"),' \
    '("Łódź Jazz Night", "d-jazz-night"),' '("Łódź Jazz Night", "lodz-jazz-night"),' \
    '("Straße der Lieder", "stra-e-der-lieder"),' '("Straße der Lieder", "strasse-der-lieder"),' \
    'def test_only_ascii_letters_and_digits_survive():' 'def test_accented_letters_keep_their_base_letter():' \
    'assert slugify("Ça va? Ñandú 東京") == "a-va-and"' 'assert slugify("Ça va? Ñandú 東京") == "ca-va-nandu"'
  edit tests/test_build.py 'assert (tmp_path / "caf-m-ller.html").is_file()' 'assert (tmp_path / "cafe-muller.html").is_file()'
}
