# ADR 0029: Teach authors with a tested example, and ship the adopted working principles

- Status: Accepted.
- Scope: Prompt and Context Design, the foundational knowledge, and the always-loaded layer other plugins' skills rely on.

## Context

The plugin is meant to carry what its trials learn to future agents that have none of this context. Two ways of carrying it were compared in two-stage trials: authors on two model families wrote an always-loaded instruction file for a user's recurring complaints, and consumer agents on both families ran twenty behavior scenarios, including counter-scenarios, under each file. Stated lessons did not transfer: about a thousand words of them made the resulting instructions slightly worse (84.2% against 88.8% of consumer runs passing), and a 173-word list changed nothing (85.0% against 84.6%). A tested example did: with the adopted working principles shown as one text that passed trials, framed as evidence of what worked rather than a template, consumers of the authors' own wording passed 94.2% against 84.6%, and in an independent replication 94.4% against 89.4%, losing no counter-scenario run, on both families; no author reproduced a sentence of the example.

Software Development's skill bodies also rely on an always-loaded layer for finishing, verification, and cleanup duties, which only one user's private file supplied.

## Decision

Prompt and Context Design carries the adopted working principles as a tested standing-instruction text, with the framing that was tested, so an agent writing instructions sees one text that passed trials and adapts it. The same text is the always-loaded layer the plugins' skills rely on; a user installs it by placing it in their host's always-loaded instruction file. The foundational knowledge records the trial findings behind the text, each with the reach of its evidence: modal keywords, a gate's extra exit, the resume trigger's family-specific wording, teaching by example, and a pushback instruction that did not produce the judgment it asked for.

## Consequences

A change to the example is untested until it runs, and the example's evidence names its families and scenarios. Records: `context/convergence-rca/experiments/teaching/README.md` and `experiments/kernel/README.md` in the maintainer's local context.
