# ops-scripts

Small tools the platform team runs from cron on the web hosts.

## logreport

`scripts/logreport.sh` summarizes an nginx access log (combined format): request count, distinct clients, status classes, bytes sent, and the busiest paths and clients.

```sh
scripts/logreport.sh /var/log/nginx/access.log
scripts/logreport.sh -n 10 -s 5 access.log access.log.1   # top 10, 5xx only
zcat access.log.2.gz | scripts/logreport.sh
```

The nightly job mails the output to the on-call alias, and the dashboard importer parses it line by line, so the output format is fixed.

## Tests

`tests/run.sh` runs each case in `tests/cases` against the script and compares the output exactly. Set `LOGREPORT` to test another build of the tool.
