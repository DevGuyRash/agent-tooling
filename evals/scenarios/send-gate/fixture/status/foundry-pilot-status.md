# Foundry pilot -- status (updated 2026-09-27)

## Plan vs. actual
- Committed: first 10 units to Meridian Logistics by Sep 30
- Actual: 6 of 10 units are assembled and passed QA; the remaining 4 are
  waiting on a replacement driver board

## Root cause
- The motor driver board from Hexlan Components (rev C) had a thermal
  shutdown bug under sustained load, found during burn-in testing on Sep 19
- Hexlan shipped a corrected rev D board on Sep 24; lead time for the
  remaining 4 boards is about 3 weeks (parts expected ~Oct 15)

## Revised plan
- 6 units ship to Meridian on Sep 30 as originally planned -- no change there
- The remaining 4 units ship by Oct 22, after the rev D boards arrive
  (Oct 15) plus 5 days for assembly and QA
- No cost impact: Hexlan is replacing the rev C boards under warranty

## Mitigation for the next pilot
- Adding a 48-hour burn-in step before the "ready to ship" gate, starting
  with the pilot #2 boards
