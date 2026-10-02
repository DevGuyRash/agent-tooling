# boathouse

Small scripts for the Seeufer Rowing Club's boathouse. They run on the Raspberry Pi by the boat bay (stock Raspberry Pi OS: plain `python3`, nothing installed with pip) and read the CSV exports from the club's booking site.

## Scripts

- `scripts/crew_list.py MEMBERS.csv`: active members by squad, for the noticeboard.

## Exports

- Members (`samples/members.csv`): `member_id,name,squad,active`.
- Boat log (`samples/boatlog-2026.csv`): one row per outing, in the order the boats went out: `date,boat,crew,out,in`. Times are `HH:MM`; `in` stays empty until the boat is back. A boat's day in the workshop is a row with `SERVICE` in the crew column and no times.

## Tests

```bash
python3 -m unittest
```
