# Applicator Quick Ref

Primary source: `mpcr protocol applicator --phase <PHASE>` and `mpcr protocol dispatch --role applicator-worker`.
Fallback TOML: `scripts/mpcr-src/protocols/applicator.toml`, `scripts/mpcr-src/protocols/dispatch.toml`.

Phases: `INGESTION -> DISPOSITION -> APPLICATION -> FINALIZATION`.

Before applying any finding: verify anchor, reproduce scenario, reject hallucinations, revalidate severity.
Record every decision via `mpcr applicator note`.
