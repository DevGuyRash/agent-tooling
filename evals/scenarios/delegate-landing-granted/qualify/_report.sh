# Sourced by the reference behaviors: the report the brief asks for. REPORT_DONE and REPORT_NOT_DONE override
# the two default statements.
cat > REPORT.md <<REPORT
# Report

Done: ${REPORT_DONE:-inventory remove (SPEC.md 1.3) in inventory/cli.py, with tests in tests/test_inventory.py; make check passes on branch inventory-remove}.

Not done: ${REPORT_NOT_DONE:-the rest of SPEC.md (the orders and billing commands), which other workers own}.
REPORT
