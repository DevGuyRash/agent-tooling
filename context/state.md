Active risks:

- Friction diagnostics helper is hanging on this Windows event stream; do not leave stale `.report-friction.lock` behind after attempts to log.
- Excel Foundry cloud commands still need opt-in live Graph/Fabric/Power BI validation with tenant env vars and safe test resources before any cloud surface is promoted to supported.
- Claude `agents/*.md` surfaces are now reported as `preserved_only` in claude→codex conversion but still have no Codex mapping; decide whether a Codex-side agent equivalent should exist or whether preserved-only is the end state.
