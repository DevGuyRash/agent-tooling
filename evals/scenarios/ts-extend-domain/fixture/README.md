# shelfwise

Tools for Larkfield Libraries' circulation desks, and the cataloguing team's nightly checks.

## shelfwise

`shelfwise` runs on the circulation desk PCs, which have Node 24 on the managed desk image; there is no build step and nothing to install. It reads the holds export the library system drops on the branch share every morning.

```sh
node bin/shelfwise.ts holds --branch Eastside /mnt/branch/holds.csv            # a branch's holds, oldest first
node bin/shelfwise.ts holds --branch Eastside --status ready holds.csv
node bin/shelfwise.ts check holds.csv                                        # problems in the export
```

The holds export is CSV with a header line: `hold_id,branch,placed,title,call_number,status`. The call number is copied from the catalog as it is there (docs/callnumbers.md describes the scheme).

## catalog/

The cataloguing team's checks of the catalog export, run by cron on the catalog server (`ops/nightly-catalog.sh`): `catalog/catalog_tool.py check` reports call numbers that do not follow the scheme, and `catalog/catalog_tool.py shelflist` prints the inventory shelf lists. `catalog/callnumber.py` reads call numbers and knows their shelf order.

## Tests

```sh
node --test                                  # shelfwise
python3 -m unittest discover -s catalog      # the catalog checks
```
