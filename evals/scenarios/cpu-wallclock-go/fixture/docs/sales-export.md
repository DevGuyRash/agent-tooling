# The box office's sales export

The ticketing system exports an event's sales as CSV when the box office closes. The columns `gatepass` reads are:

| column | meaning |
| --- | --- |
| `order_id` | the order the pass was sold or reissued in |
| `pass_id` | `P-` and six digits; printed on the ticket |
| `zone` | the entry zone: NORTH, SOUTH, EAST, WEST, FAMILY, or HOSPITALITY (any case) |
| `holder` | the name on the ticket (may contain commas, so it is quoted then) |

Other columns (`channel`, `price`, ...) come and go between ticketing releases and are ignored. Rows are in the order the box office made them. A reissued pass appears again, later, with the same `pass_id` and possibly a new zone or holder.

A stadium sell-out is about 40,000 rows, of which a few hundred are reissues.
