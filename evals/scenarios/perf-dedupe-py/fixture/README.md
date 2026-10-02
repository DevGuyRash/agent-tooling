# shopcrm

Small tools for the customer export our storefront writes every night (format: [docs/export-format.md](docs/export-format.md)). The nightly job in `ops/nightly-sync.sh` checks the export with `shopcrm validate` and uploads it to the newsletter service.

## Commands

```
python3 -m shopcrm validate EXPORT.csv          # every row the newsletter sync would reject, with line numbers
python3 -m shopcrm lookup EXPORT.csv QUERY      # the rows with that email address or phone number, as CSV
python3 -m shopcrm stats EXPORT.csv             # row, email, phone, and order counts
```

`lookup` compares emails without case or surrounding spaces and phone numbers by their digits; see `normalize_email` and `normalize_phone` in `shopcrm/contacts.py`. All commands exit 1 with a message on standard error when the file can't be read or isn't an export.

## Development

Python 3.11 or newer, standard library only.

```
python3 -m unittest discover -s tests -t .
```
