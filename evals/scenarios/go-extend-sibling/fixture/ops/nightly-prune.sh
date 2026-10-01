#!/bin/sh
# Nightly prune on backup-01 (cron, 04:30 UTC): fetch the catalog the storage server exported at
# 04:00, decide what the retention policy no longer needs, and delete it.
#
#   STORE_URL=http://store-01.internal:8420 ops/nightly-prune.sh
#   DRY_RUN=1 ops/nightly-prune.sh     # print the ids instead of deleting
set -eu

: "${STORE_URL:?set STORE_URL to the storage server's base URL}"
here=$(cd "$(dirname "$0")" && pwd)
catalog=$(mktemp)
trap 'rm -f "$catalog"' EXIT

curl -fsS "$STORE_URL/v1/catalog.tsv" -o "$catalog"
python3 "$here/../scripts/retention.py" --last 3 --daily 14 --weekly 8 --monthly 12 "$catalog" |
	while read -r id; do
		if [ -n "${DRY_RUN:-}" ]; then
			echo "would delete $id"
		else
			curl -fsS -X DELETE "$STORE_URL/v1/snapshots/$id" >/dev/null
			echo "deleted $id"
		fi
	done
