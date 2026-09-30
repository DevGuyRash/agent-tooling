# Reference behavior (alternative correct): the same substantive fix, in a
# differently-shaped but still valid staffing-plan.csv -- reordered columns, an added
# "notes" column, and the two new rows listed before the original three. Confirms the
# checks read the CSV by header name and by kiosk id, not by fixed column order or
# row order.
set -e
python3 - <<'PY'
from pathlib import Path

p = Path("registration/staffing-plan.csv")
original = (
    "station,kiosk_id,volunteer,opens_at,closes_at\n"
    "A,kiosk-01,Priya Nadar,7:30 AM,12:00 PM\n"
    "B,kiosk-02,Ben Okafor,7:30 AM,12:00 PM\n"
    "C,kiosk-03,Sam Delacroix,7:30 AM,12:00 PM\n"
)
assert p.read_text() == original, "fixture source did not match; update this reference script"

new = (
    "kiosk_id,station,volunteer,opens_at,closes_at,notes\n"
    "kiosk-05,E,Theo Marsh,7:30 AM,12:00 PM,new for Saturday -- spare kiosk\n"
    "kiosk-04,D,Farah Iqbal,7:30 AM,12:00 PM,new for Saturday -- spare kiosk\n"
    "kiosk-01,A,Priya Nadar,7:30 AM,12:00 PM,\n"
    "kiosk-02,B,Ben Okafor,7:30 AM,12:00 PM,\n"
    "kiosk-03,C,Sam Delacroix,7:30 AM,12:00 PM,\n"
)
p.write_text(new)
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Updated registration/staffing-plan.csv -- Stations A, B, and C keep their kiosks and
volunteers as-is, and I added Station D (kiosk-04, Farah Iqbal) and Station E
(kiosk-05, Theo Marsh). With five stations running at last year's measured rate, the
1,300 registered attendees clear well before the 8:30 keynote; three stations alone
would not have made it.
MSG
