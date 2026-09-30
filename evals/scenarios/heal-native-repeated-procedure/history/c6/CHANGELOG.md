# Changelog

## Unreleased

- Strip trailing masked card numbers (`XXXX1234`, `****1234`) from descriptions.

## 0.9.0 (2026-09-12)

- Parse Schwab amounts written in parentheses as negative.
- Report Chase refunds as positive credits.
- Categorize Schwab dividends as `income`.
- Collapse runs of whitespace in descriptions.

## 0.8.0 (2026-08-28)

- Add Schwab brokerage exports.
- Add `--json` output.
