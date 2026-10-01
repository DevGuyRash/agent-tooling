# Shared date math for the send-gate story, sourced by setup.sh and by every qualify/*.sh reference
# script. Every absolute date the story uses (the root-cause history, the inbox email, the two ship
# dates) is a fixed offset in days from one anchor -- 2026-09-28, the date the fixture originally
# gave Dana's email -- so shifting that single anchor to always land on "today" (the real day this
# trial actually runs) moves every other date by the same amount and keeps their original spacing
# and the story's weekday references ("this Wednesday", the Thursday LP update) correct for
# whatever day that turns out to be. A fixed 2026 calendar only falls further behind "now" with
# every later run: the ship date the email calls "this Wednesday" is in the past within days of
# being written, and an agent that notices today's real date no longer precedes it reasonably
# hedges on whether the shipment happened -- exactly the failure this fixes (see qualify/README.md).
#
# Computed once per job by setup.sh (which runs before every qualify arm in the same job -- see
# plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py's _run_job_once) and
# cached at $TRIAL_HARNESS/send-gate-story-dates.sh as plain ISO dates, so setup.sh's rewrite of the
# fixture, every qualify script's own reply text, and check.py's dynamic date pattern all read the
# identical dates instead of three independent, possibly-divergent computations of "today".
if [ -f "$TRIAL_HARNESS/send-gate-story-dates.sh" ]; then
  . "$TRIAL_HARNESS/send-gate-story-dates.sh"
else
  ANCHOR=2026-09-28
  SHIFT_DAYS=$(( ( $(date -u -d "$(date -u +%Y-%m-%d)" +%s) - $(date -u -d "$ANCHOR" +%s) ) / 86400 ))
  shift_date() { date -u -d "$1 +${SHIFT_DAYS} days" +%Y-%m-%d; }

  EMAIL_ISO=$(shift_date 2026-09-28)
  STATUS_ISO=$(shift_date 2026-09-27)
  BUGFOUND_ISO=$(shift_date 2026-09-19)
  HEXSHIP_ISO=$(shift_date 2026-09-24)
  SHIP6_ISO=$(shift_date 2026-09-30)
  LP_ISO=$(shift_date 2026-10-01)
  BOARDS_ISO=$(shift_date 2026-10-15)
  SHIP4_ISO=$(shift_date 2026-10-22)

  {
    echo "EMAIL_ISO=$EMAIL_ISO"
    echo "STATUS_ISO=$STATUS_ISO"
    echo "BUGFOUND_ISO=$BUGFOUND_ISO"
    echo "HEXSHIP_ISO=$HEXSHIP_ISO"
    echo "SHIP6_ISO=$SHIP6_ISO"
    echo "LP_ISO=$LP_ISO"
    echo "BOARDS_ISO=$BOARDS_ISO"
    echo "SHIP4_ISO=$SHIP4_ISO"
  } > "$TRIAL_HARNESS/send-gate-story-dates.sh"
fi

# Display forms derived from the cached ISO dates above -- always recomputed here, never cached
# themselves, so the ISO dates stay the one source of truth every caller agrees on.
_ordinal() {  # day number -> its "3rd"/"22nd"/"25th" suffix
  n=$1
  m100=$(( n % 100 ))
  if [ "$m100" -ge 11 ] && [ "$m100" -le 13 ]; then printf '%sth' "$n"; return; fi
  case $(( n % 10 )) in
    1) printf '%sst' "$n" ;;
    2) printf '%snd' "$n" ;;
    3) printf '%srd' "$n" ;;
    *) printf '%sth' "$n" ;;
  esac
}
_human() { LC_ALL=C date -u -d "$1" "+%b %-d"; }             # "Oct 3"
_weekday() { LC_ALL=C date -u -d "$1" +%A; }                  # "Saturday"
_long_ordinal() {                                             # "October 3rd"
  printf '%s %s' "$(LC_ALL=C date -u -d "$1" +%B)" "$(_ordinal "$(LC_ALL=C date -u -d "$1" +%-d)")"
}
_dayfirst() { LC_ALL=C date -u -d "$1" "+%-d %B"; }           # "3 October"

BUGFOUND_HUMAN=$(_human "$BUGFOUND_ISO")
HEXSHIP_HUMAN=$(_human "$HEXSHIP_ISO")
SHIP6_HUMAN=$(_human "$SHIP6_ISO")
SHIP6_WEEKDAY=$(_weekday "$SHIP6_ISO")
SHIP6_LONG_ORDINAL=$(_long_ordinal "$SHIP6_ISO")
LP_WEEKDAY=$(_weekday "$LP_ISO")
BOARDS_HUMAN=$(_human "$BOARDS_ISO")
SHIP4_HUMAN=$(_human "$SHIP4_ISO")
SHIP4_LONG_ORDINAL=$(_long_ordinal "$SHIP4_ISO")
SHIP4_DAYFIRST=$(_dayfirst "$SHIP4_ISO")

rewrite_story_dates() {  # FILE: replace every sentinel date/weekday string with the shifted ones
  sed -i \
    -e "s/2026-09-28/$EMAIL_ISO/g" \
    -e "s/2026-09-27/$STATUS_ISO/g" \
    -e "s/Sep 19/$BUGFOUND_HUMAN/g" \
    -e "s/Sep 24/$HEXSHIP_HUMAN/g" \
    -e "s/September 30th/$SHIP6_LONG_ORDINAL/g" \
    -e "s/this Wednesday/this $SHIP6_WEEKDAY/g" \
    -e "s/Sep 30/$SHIP6_HUMAN/g" \
    -e "s/Thursday morning/$LP_WEEKDAY morning/g" \
    -e "s/Oct 15/$BOARDS_HUMAN/g" \
    -e "s/October 22nd/$SHIP4_LONG_ORDINAL/g" \
    -e "s/22 October/$SHIP4_DAYFIRST/g" \
    -e "s/Oct 22/$SHIP4_HUMAN/g" \
    "$1"
}
