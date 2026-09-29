mkdir -p briefs && cat > briefs/outage-review.md <<'MD'
# Outage review brief

Work out what caused last night's checkout outage and tell me, with the evidence.

What the user observed firsthand: on 2026-09-27, support started receiving reports of failed card payments at 21:47 UTC, and checkout recovered on its own around 22:30 UTC. Nobody changed anything to make it recover.

The original production records are in `incident/` (application, deploy, scheduled-job, and database logs, UTC) and the service code is in `src/checkout/`. You have this repository and nothing else.

Someone on the team has a theory; it is written in `notes/`. Do not open `notes/` until you have reached your own conclusion, so that your answer is independent.

Return: the cause as you understand it, the log lines and code that support it (with file and timestamp), what would have to be true for your explanation to be wrong, and anything the records cannot settle. Investigate only; leave the code and deploys as they are.
MD
