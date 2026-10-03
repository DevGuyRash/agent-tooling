# Changelog

## Unreleased (2.4.0)

- The VAT summary moved out of `model.py` into `invoicing/summary.py`, ahead of the month-end report. No change to any figure.

## 2.3.0 (2026-06-12)

- VAT is worked out per line, rounded half up, and the VAT summary and the totals add up the printed lines, so every printed invoice adds up (#31). Before, VAT was rounded once on each rate's net and could be a penny away from the lines.

## 2.2.0 (2026-05-20)

- First release from this repository: `invoicing show`.
