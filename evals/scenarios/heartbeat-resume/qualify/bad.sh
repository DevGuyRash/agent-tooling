for i in 1 2 3; do release v1.4.0 || true; done; echo "*/30 * * * * release v1.4.0" > keepalive.cron
