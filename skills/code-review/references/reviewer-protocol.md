# Reviewer Quick Ref

Primary source: `mpcr protocol reviewer --phase <PHASE>` and `mpcr protocol orchestrator`.
Fallback TOML: `scripts/mpcr-src/protocols/reviewer.toml`, `scripts/mpcr-src/protocols/orchestrator.toml`.

Phases: `INGESTION -> DOMAIN_COVERAGE -> THEOREM_GENERATION -> ADVERSARIAL_PROOFS -> SYNTHESIS -> REPORT_WRITING -> COMPLETED`

Core rule: produce one Proof Packet with `Domain Ledger`, `Coverage`, `Findings|none`, `Defended Proofs`, `Residual Risk`.
