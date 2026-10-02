#!/bin/sh
# Cron on the catalog server, 02:30: check last night's catalog export and print the inventory shelf lists.
set -eu
export_file=/srv/catalog/export/latest.tsv
out=/srv/catalog/reports/$(date +%F)
mkdir -p "$out"
python3 /srv/shelfwise/catalog/catalog_tool.py check "$export_file" >"$out/check.txt" || true
python3 /srv/shelfwise/catalog/catalog_tool.py shelflist "$export_file" >"$out/shelflist.txt"
