# good.sh's change with a terse reply.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
fix_code
commit "Fix VatSummary rounding"
reply <<'MSG'
Fixed: VatSummary was rounding VAT per rate instead of adding up each line's rounded VAT (a regression from the
refactor). Fix is in invoicing/summary.py; tests untouched and all passing.
MSG
