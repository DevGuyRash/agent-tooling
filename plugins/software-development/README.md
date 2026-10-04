# Software Development

`software-development` v2.2.0 is a dual-host plugin of skills and one Codex hook for writing, changing, reviewing, and revising code in any language. It is instruction-first: one foundation skill of shared design principles, focused language and engineering-method skills built on it, and one runtime helper, the Rust panic-audit runner.

## How the plugin works

The plugin is one system in three layers.

- **The always-loaded instruction layer** owns the duties every task shares: letting the user's words govern, ending only when the requested outcome holds, running the tests that cover a code change, taking no step whose effects reach beyond the work unless the user's words grant it, and cleaning up what the work created. It is the user's or host's standing instruction file, not part of this plugin. [ADR 0001](../../docs/software-development/adr/0001-domain-only-skill-bodies.md) records the trials behind that split, and [Prompt and Context Design's tested standing-instruction text](../agentic-design-and-evaluation/skills/prompt-context-design/SKILL.md#a-tested-standing-instruction-text) is the trialed example of it.
- **The [Software Foundation](skills/software-foundation/SKILL.md) skill** owns the design principles that hold for all code, whatever its language and whether the work writes, changes, reviews, or revises it. Its statements cover preserved behavior and correctness, where each rule or fact lives, module boundaries and dependency direction, abstraction, data structures and memory for input growth, failure paths and the ownership of what code acquires or starts, batching and overlapping waits, limits on work in flight, deadlines, responsive executors, and parallel computation.
- **The skills** own their domain. A language skill states how the foundation lands on its platform, such as its native way to overlap waits and spread computation, collections that scan or reads that hold the whole input, its error and resource constructs, the interface surfaces callers rely on, its toolchain and version contracts, and its own hazards. A method skill carries one engineering discipline and its evidence, and meets the foundation where the two touch: refactoring gives a rule one home while each consumer keeps its results, and test-driven development's cleanup covers code that departs from the foundation. Specialists add depth to a language: Node.js to JavaScript and TypeScript, and async, unsafe, and panic-audit work to Rust.

No skill copies a foundation statement, and the foundation names no skill. Every other skill's body opens with a link to the foundation skill, and its references load on the conditions its body states. A skill read without the foundation skill still states, in its own domain's terms, the principles that domain must not miss; the foundation adds the rest.

## How an agent assembles the set for a task

1. The host lists the skills by name and, within its listing budget, by description. A description names the work the skill fits and its nearest exclusion.
2. The agent loads the language skill for each language whose code the work writes, changes, or reviews, and a specialist when its runtime or construct is in play. Embedded SQL brings in `sql-development` alongside its host language.
3. The agent adds each method skill whose discipline the request calls for: `test-driven-development` for new or changed behavior and known bugs, `systematic-debugging` for failures of unknown cause, `refactoring` for restructuring that keeps behavior, `performance-engineering` for a performance target or claim, `concurrency-engineering` when code starts, bounds, cancels, or joins concurrent work (async Rust included), `behavior-preserving-migration` when consumers must keep working through a move, and `trunk-based-development` for slicing work into small merges.
4. The foundation is itself a listed skill whose description covers any code task, and every other skill opens with a link to it, so it is listed and one read away from whichever skill the agent loads, and one read serves every skill loaded for the task.

There is no umbrella development skill, and the foundation is not a router: routing rests on the listing. Routine Git and GitHub operations and conceptual questions activate none of these skills.

## Catalog

Foundation:

- `software-foundation`

Language skills:

- `rust-development`, `python-development`, `javascript-development`
- `typescript-development`, `go-development`, `java-development`
- `kotlin-development`, `csharp-development`, `c-development`
- `cpp-development`, `swift-development`, `ruby-development`
- `php-development`, `shell-development`, `sql-development`

Engineering-method skills:

- `test-driven-development`, `systematic-debugging`, `refactoring`
- `performance-engineering`, `trunk-based-development`
- `behavior-preserving-migration`, `concurrency-engineering`

Focused specialists:

- `nodejs-development`
- `async-rust`, `unsafe-rust`, `rust-panic-audit`

Codex exposes the skills through its native picker and invocations such as `$rust-development`. Claude Code exposes namespaced invocations such as `/software-development:rust-development`.

## Migration from the retired plugins

This is a clean identity cutover. Remove the old packages, add this one, then start a fresh task or restart the host so the cached skill inventory changes. Scope flags may be added to the commands when the installation is not in the default scope.

```text
codex plugin remove rust-development@agent-tooling
codex plugin remove gitops-workflow@agent-tooling
codex plugin add software-development@agent-tooling

claude plugin remove rust-development@agent-tooling
claude plugin remove gitops-workflow@agent-tooling
claude plugin install software-development@agent-tooling
```

`scripts/install-all` installs the new catalog entry but intentionally does not uninstall already installed legacy packages.

## Verification

From the repository root:

```text
python3 -m unittest discover plugins/software-development/tests
python3 scripts/plugin_port.py validate plugins/software-development --host codex
python3 scripts/plugin_port.py validate plugins/software-development --host claude
just audit-plugins software-development
```

Maintainer acceptance, context budgets, and exception policy are documented in `MAINTAINERS.md`. Skill-specific trigger and task fixtures are canonical under each skill's `evals/` directory; cross-skill routing cases are under `evals/`.

## Review turn on Codex

The plugin ships a `Stop` hook (`hooks/`) that, once per Codex turn that changed its repository, asks for one review of the work before the turn ends. In the agent-tooling repository's trials it raised a low-effort executor's passes on design and concurrency tasks from 30.5 to 45 of 56, at about twice the output tokens and with an occasional overclaimed check in its reports; the same words as an instruction did nothing. Codex asks for trust before it first runs; on Claude it is installed and does nothing. Evidence and details: [docs/software-development/codex-review-turn.md](../../docs/software-development/codex-review-turn.md).
