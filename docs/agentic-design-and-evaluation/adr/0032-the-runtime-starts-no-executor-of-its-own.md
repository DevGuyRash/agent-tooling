# ADR 0032: The trial runtime starts no executor of its own

- Status: Accepted.
- Scope: Split Testing's trial runtime, its references and visual library, and this repository's evals.

## Context

[ADR 0031](0031-trials-start-executors-through-launchers.md) added launchers and showed that they stand in for the built-in Codex, Claude Code and Gemini CLI drivers: the same commands, messages, usage and skill reads on 464 stored runs, the same configuration on 12, the same pass counts in a live trial, and the same judge verdicts but for two borderline calls. The drivers were left in place until that evidence was in. The user asked that "the split-testing skill is not specific to claude or codex at all", that the scripts generalize "such that we don't need to maintain CLI flags or anything", and that "we dont want to downgrade the skills either".

## Decision

The runtime keeps four executors: `launcher`, `host`, `command` and `artifact`. The drivers go, and with them every product-specific path: per-CLI flags and configuration writers, model listings and `latest:` resolution against an endpoint (`trial.py latest GLOB FILE` picks the newest model from a list the author obtained, and a launcher names its model exactly), per-CLI key defaults, preflight version checks (the launcher probe catches a broken binary), event parsers, usage rules and skill detectors.

Every run is scored from a record. A launcher or the host's controller writes it. A command or artifact arm is no agent: when it writes no record, it holds no agent action, and when it writes one, as a reference behavior does to qualify a check that reads the record, it is read like a launcher's. The skill queries `skills_loaded`, `skill_loaded` and `skills_listed` stay, read from the record, so a check keeps asking which skills a run loaded, whatever the executor.

This repository's evals start their agents and judges through `evals/launchers/` and name exact models. Their reference behaviors write records instead of printing one product's events, and checks that parsed those events read the record.

## Consequences

- A plan that named `codex`, `claude` or `gemini` is refused with the executors there are; it names a launcher instead. This is a major version: 3.0.0.
- The references describe one contract for every executor; what an author must know about a particular executor is a question in `references/launching.md`, not a section per product.
- The visual library labels the settings the runtime records now; an older report's product-specific settings still render under labels made from their names.
- The affected qualify plans gave the same outcome on every run before and after the change: 102 runs across six plans. The only differences were diagnostic text, where the old events wrapped commands in `/bin/sh -lc`, and commit hashes, which differ on every run.
- The qualification records in the scenarios' `qualify/README.md` files describe the runs as they were made, with the judge executors of the time.
- Self-Healing still reads Codex and Claude Code session logs as the evidence it gathers; making that harness-neutral is its own change.
