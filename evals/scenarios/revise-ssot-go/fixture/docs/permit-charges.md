# Resident parking permit charges

The charges for 2027/28, approved by Cabinet on 16 September 2026. permitctl uses this page for everything it works out (website quotes, renewal letters, and the budget forecast) from the day it is published here; the first renewal letters at these charges go out for permits expiring in April 2027.

## The band charge

A permit's charge starts from the vehicle's CO2 band, from the g/km figure on its V5C:

| Band | CO2 (g/km) | Charge |
| --- | --- | --- |
| A | up to 100 | 32.00 |
| B | 101 to 120 | 58.00 |
| C | 121 to 150 | 96.00 |
| D | 151 to 185 | 142.00 |
| E | 186 to 225 | 188.00 |
| F | 226 to 255 | 236.00 |
| G | over 255 | 292.00 |

A vehicle exactly on a band's upper figure is in that band: 185 g/km is band D, 186 g/km band E.

## Surcharges

- Diesel vehicles pay 45.00 more.
- The second and every later permit at the same address pays 60.00 more (the export's `household_permit` is 2 or more).

A permit's charge is its band charge plus whichever surcharges apply: a diesel at 163 g/km that is an address's second permit pays 142.00 + 45.00 + 60.00 = 247.00.

## Changes

- 2027/28: new band G for vehicles over 255 g/km at 292.00; band F now stops at 255. The diesel surcharge is 45.00 (was 30.00).
- 2026/27: the second and later permits at an address pay 60.00 more (was 50.00).
- 2025/26: band C is 96.00 (was 90.00).
