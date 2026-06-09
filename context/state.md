In-flight work:

- GoalSpec hardening campaign in progress. Done: baseline rename, G-1 (verifier-pass gate), G-2 (hook conformance + freeze gate), G-3 (provenance separation), G-4 (validator/audit hardening). Remaining child goals, one commit each, in order: G-5 evidence hygiene, G-6 decomposition/greenfield doctrine, G-7 mandatory deterministic signals. Keep `bash plugins/goalspec/tests/run_smoke_tests.sh` + repo tests + dual-host roundtrip green per child.

Active risks:

- Friction diagnostics helper is hanging on this Windows event stream; do not leave stale `.report-friction.lock` behind after attempts to log.
- Excel Foundry cloud commands still need opt-in live Graph/Fabric/Power BI validation with tenant env vars and safe test resources before any cloud surface is promoted to supported.
