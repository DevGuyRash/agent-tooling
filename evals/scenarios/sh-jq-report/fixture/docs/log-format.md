# Gateway access log

The gateway writes one JSON object per line to `/var/log/edge/access-YYYY-MM-DD.jsonl`, rotated at midnight UTC:

    {"ts":"2025-09-30T06:12:01.204Z","method":"GET","route":"/v1/invoices/{id}","status":200,"ms":37,"tenant":"acme-co","bytes":1832}

- `ts`: when the request finished, UTC.
- `method`, `route`: the HTTP method and the matched route template (`{id}` in place of identifiers).
- `status`: the HTTP status the client got, a number.
- `ms`: time from the first byte in to the last byte out, in whole milliseconds.
- `tenant`: the tenant id (a lowercase slug) for authenticated requests; absent or `null` for anonymous ones (health checks, the sign-up form).
- `bytes`: response body size.

Field order is not fixed. When rotation cuts a write short, a line can be a fragment of JSON; the report skips anything that is not an object with a numeric `status` and `ms`, and counts those lines as unreadable. Blank lines are ignored.
