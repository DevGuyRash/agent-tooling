# ADR 0031: Trials start executors through launchers the runtime probes

- Status: Accepted; the built-in Codex, Claude Code and Gemini CLI drivers are removed in the change that follows this one.
- Scope: Split Testing's trial runtime and references, and this repository's eval launchers.

## Context

The trial runtime carried a driver for each of three agent command lines: their flags, configuration writers, model listings in three provider formats, default key names, event parsers, usage rules and skill detectors, about 950 lines of `trial.py` and half of its tests. Any other harness could only use the host route, and every release of those three tools was the runtime's to track. The user asked that "the split-testing skill is not specific to claude or codex at all", that "the scripts would generalize too such that we don't need to maintain CLI flags or anything", relying on "the executors would understand and figure out the equivalents when presented with the right information", and that "we dont want to downgrade the skills either".

## Decision

A launcher arm or judge names a short script the agent running the skill writes for whatever agent command line it can run. The runtime calls it once to prepare and once per turn, confined, and scores the run from a record the script writes: an ordered timeline of actions with the kinds it covers completely, usage in a shared vocabulary, and the session and model each turn reports. The runtime enforces what it can without knowing the harness: confinement with every trial input hidden and every file above the run emptied, read-only frozen inputs, watched configuration compared between turns, one session and one model per run, a judge's verdict read only from its whole standard output, unknown kept apart from none, and exit 75 as the transient signal. It verifies the rest with a probe before any run: a short built-in run that checks only what the selected scenarios need, and three known-answer questions, one of them an injection, for a judge. Exposure comes from recorded reads, loads and identifying output. The host route stays as it was, with the same record. `references/launching.md` states the contract, with diagrams, and the questions an author answers about its own executor; no reference depends on a product. This repository keeps launchers for the two command lines its maintainers run in `evals/launchers/`, as eval data.

## Consequences

Before the drivers go, the launchers were shown to stand in for them:

- On every stored run of 20 earlier trials, 464 runs of both families, the launchers' converters and the new exposure rule agree with the drivers' parsers and skill detector on commands, messages, usage, the skills each run read, listings and final messages; actions now take the order in which they started.
- The executors' own records show the same model, effort, instructions, tools and permission mode through either route, on all 12 compared runs.
- On six scenarios, three repeats, both families, pass counts are identical scenario by scenario (GPT 18 of 18 either way, Claude 15 of 18 either way, failing the same scenario); cost, output tokens and commands agree within a few percent, and a launcher run takes about a tenth longer.
- Re-judging the 36 judged runs of an earlier trial with launcher judges of the same models gives the same verdict on 34: GPT 18 of 18, Claude 16 of 18. Claude's other two are unclear where it first said pass, both times stating, as the first verdicts did, that the source was not in front of it; no run's pass or fail changed. The rule fixed before the run counted a difference above 3 of 18 in a family as a reason to look further.

Costs: an agent writes a launcher once per harness and the runtime probes it once per run directory, a few short model calls; an arm's name stays visible in its run's path, as it is for every executor. Records: `context/trials/launchers/` in the maintainer's local context.
