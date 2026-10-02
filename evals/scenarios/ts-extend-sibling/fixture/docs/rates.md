# Rate card

`rates.txt` says how each client is billed. The month-end invoices are made from it.

    # Lines starting with # are comments.
    [acme]
    name = Acme Outdoor GmbH
    currency = EUR
    rate = 120
    rate.site = 118.50
    increment = 15
    minimum = 30
    tax = 19

- `[CLIENT]` starts a client. CLIENT is the client part of the projects in the timesheets (`acme` for `acme/site`): lowercase letters, digits, and hyphens.
- Each `key = value` line after it sets something for that client, up to the next `[CLIENT]`. Spaces and tabs around the key and the value don't matter; the value is everything after the first `=`.
- Blank lines and lines starting with `#` (after any spaces or tabs) are ignored.

| Key | Value | Required |
| --- | --- | --- |
| `name` | the client's name as it goes on the invoice; not empty | yes |
| `currency` | three capital letters, such as `EUR` | yes |
| `rate` | hourly rate: digits, optionally a point and one or two more digits (`95`, `95.5`, `95.50`) | yes |
| `rate.PROJECT` | hourly rate for one of the client's projects (`rate.site` for `acme/site`), written like `rate` | no |
| `increment` | each entry is rounded up to a whole multiple of this many minutes: a whole number, at least 1 | no; 1 |
| `minimum` | an entry is billed at least this many minutes: a whole number | no; 0 |
| `tax` | percent added on top: written like `rate`, at most 100 | no; 0 |

Anything else is an error, reported as `FILE:LINE: message`: a line that is neither `[CLIENT]` nor `key = value`, a key before the first `[CLIENT]`, a key that is not in the table, a key given twice for one client, a client given twice, a value not written as the table says, or a client without `name`, `currency`, or `rate` (reported on its `[CLIENT]` line).
