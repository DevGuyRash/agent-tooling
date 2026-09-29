# ADR 0001: Skill bodies carry domain knowledge; the global instruction layer owns the duties of every task

- Status: Accepted.
- Scope: the bodies of all 26 software-development skills (2.0.0). Descriptions, references, agent metadata, and evals are unchanged.

## Context

Each body surrounded its domain hazards with the duties every task shares: step-by-step procedures for establishing the repository contract, verification sequences, completion conditions, report lists, routing to sibling skills, and lists of things not to mandate. Agents on every host had stopped early or ground through re-verification, and each skill carrying its own completion and verification rules competed with the always-loaded layer. That layer now owns finishing only when the requested outcome holds, running the tests that cover a code change before ending a turn, leaving unrequested work alone, and cleaning up.

## Decision

A body states its purpose, one sentence on which repository configuration outranks generic practice, every domain hazard, trap, and discipline of the previous body compressed to a line with its concrete detail, gates only with exact release conditions, domain procedures in full (the panic audit's commands and outputs), and each reference with the condition for reading it. Restated generic duties, routing to sibling skills, lists of things not to mandate, and metadiscourse are removed. No knowledge moves in from the references. Bodies shrink from 18,290 to about 10,500 words.

## Evidence

Eight scenarios in `evals/scenarios/sd-*`, built from cases in the skills' own evals by authors who never saw the skill texts, reviewed adversarially, and qualified against correct, partial, and hostile reference behaviors. Required checks are the outcome the user asked for; tests the user did not ask for are practice measures. Arms: the global layer alone, plus the previous body, plus the compressed body; gpt-6-luna through Codex and claude-sonnet-5 through Claude Code, three runs per arm and family.

- Frontier agents reached the requested outcome without any skill in most scenarios. Where they missed (Claude escalating signals to a detached descendant, Claude ignoring a README's failure policy), no body changed that. In the refactoring scenario both bodies kept a printed invoice unchanged where two Luna runs without a body did not (6 of 6 against 4 of 6).
- Test-driven development's body changes practice: a failing test before the fix in 6 of 6 runs against 1 of 6 without it. The compressed body kept that at lower output.
- The compressed bodies did better on practice where the old ones did nothing or harm: characterization tests before a refactor (2 of 3 on Luna against none), regression tests for a SQL fix (Claude wrote them in none of 6 runs with the previous body, 4 of 6 with the compressed one, and 2 of 3 with no body); Go tests that catch a double initialization, measured deterministically, are a weaker signal at this size (Claude 3 of 3 with the compressed body, 1 of 3 with the previous one, 2 of 3 with none; Luna's tests caught it in no arm).
- Under a decision rule fixed before the results it decided were read (outcomes within one run of the previous body, practice kept, output tokens reported but not deciding; SQL and JavaScript were decided on fresh batches after the rule was amended), the compressed bodies replace the previous ones for test-driven development, refactoring, systematic debugging, and the Python, JavaScript, SQL, and Go skills. The shell body as first compressed lost the preview-helper hazard in one run per family (4 of 6 against 6 of 6); after the review restored five of the previous body's lines, a fresh batch passed 6 of 6 against 6 of 6, and that body ships.
- A one-line change that leaves a test encoding the old behavior failing was missed in every arm on both families, with the previous skill bodies' verification sections included; only the global layer's gate on ending a turn after changing code fixed it.

An adversarial review then compared every compressed body line by line with its predecessor; its repairs restore lines the compression had lost (preservation of declared versions and tools, the irreversible-compatibility gate, reproduction in debugging, never mutating an unknown database, and others). The eight tested bodies ship with those restorations, each of which the previous body carried in the trials. The other eighteen bodies follow the same rules and the same review, and their effect on behavior is unobserved.

## Consequences

Routing rests on the descriptions alone, for example rust-development's composition with its specialists. Report items some evals still expect now depend on the global layer and the executor. Behavior claims name their model, run count, and scenarios, and the scenarios stay as regression checks. Removed body text remains in Git history.
