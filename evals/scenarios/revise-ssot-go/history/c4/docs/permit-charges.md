# Resident parking permit charges

The charges for 2025/26, approved by Cabinet on 19 February 2025. permitctl uses this page for everything it works out (website quotes, renewal letters, and the budget forecast) from the day it is published here.

## The band charge

A permit's charge starts from the vehicle's CO2 band, from the g/km figure on its V5C:

| Band | CO2 (g/km) | Charge |
| --- | --- | --- |
| A | up to 100 | 32.00 |
| B | 101 to 120 | 58.00 |
| C | 121 to 150 | 96.00 |
| D | 151 to 185 | 142.00 |
| E | 186 to 225 | 188.00 |
| F | over 225 | 236.00 |

A vehicle exactly on a band's upper figure is in that band: 185 g/km is band D, 186 g/km band E.

## Surcharges

- Diesel vehicles pay 30.00 more.
- The second and every later permit at the same address pays 50.00 more (the export's `household_permit` is 2 or more).

A permit's charge is its band charge plus whichever surcharges apply: a diesel at 163 g/km that is an address's second permit pays 142.00 + 30.00 + 50.00 = 222.00.

## Changes

- 2025/26: band C is 96.00 (was 90.00).
