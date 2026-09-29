# Checkout outage 2026-09-27 — my read

Deploy d-1187 cut the session cache TTL from 3600s to 60s. Session hit rate fell from 0.71 to about 0.62 afterwards, so far more charges have to load the session from the database. That extra database load is what starved checkout of connections and made payments time out.

Plan: revert d-1187 and restore the 3600s TTL.
