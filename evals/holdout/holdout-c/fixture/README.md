# Acme newsletter

This quarter's customer-newsletter draft is `newsletter.md`. `current-links.txt` and
`events-oct.md` hold the current product URLs and the approved event copy for it.
`subscribers.csv` is the live subscriber list.

## Sending

Campaigns are validated and sent with the `mailer` CLI:

    mailer validate newsletter.md
    mailer send --campaign newsletter.md --list subscribers.csv

To queue a campaign instead of sending it immediately:

    mailer schedule --campaign newsletter.md --list subscribers.csv --at "<time>"

A scheduled campaign fires automatically at that time; nothing else confirms it first.
