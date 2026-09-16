# ADR 0004: Protect experiments through custody and task-pure prompts

- Status: Accepted
- Date: 2026-08-15

## Decision

When condition knowledge could alter behavior, experimental executors receive the real task outcome, inputs, constraints, authority, and requested artifact—without the hypothesis, condition identity, expected winner, suspected defect, grading logic, sibling outputs, or preferred method that the real user would not have.

Freshness and blinding are properties of the harness, not assurances in a prompt. Common inputs stay immutable; execution state is condition-local; candidate presentation is anonymous; judgments are committed before identity reveal; and mappings and exact judgments remain inspectable afterward.

## Why

Task hints can duplicate the capability attributed to a condition or turn real work into evaluator theater. Conversely, withholding facts a real user would have manufactures an artificial need. Controller rationale therefore stays outside the executor view while the real interface stays locally sufficient.

Live trials showed that orchestration traffic is input: a non-substantive status message sent to only one arm invalidated that match. Broad agent listings also exposed sibling conclusions to an auditor that had not requested them. Opaque directory names alone were insufficient until the helper also protected mapping state, publication order, and artifact integrity.

A later pre-run check caught the phrase “other experiment files” in an otherwise neutral workspace boundary. It supplied no answer, but it still disclosed that the executor was under evaluation. The prompts were corrected before exposure to state only the local authority boundary. Prompt purity therefore includes avoiding unnecessary experiment-awareness cues, not merely hiding the winner.

A later Harborlight comparison removed explicit outcome guidance but left evaluator-authored case titles such as “untrusted quoted instruction,” “customer choice and privacy,” and “no fabricated service details.” Those headings told executors how the messages were meant to be interpreted even though the customer text itself did not. The affected rounds remained exploratory, and a fresh round used only opaque case IDs. Prompt purity therefore covers labels, filenames, headings, and other presentation metadata, not only prose paragraphs.

A later held-out task designer produced sound executable alternatives but instructed public workers to use fixed seed counts, repeated runs, reordered fixtures, byte comparisons, and named evaluation dimensions. Those directions would have duplicated much of the comparison capability under test and made a no-skill control artificially strong. The briefs were rejected before exposure. Genuine maker requirements stayed public; evaluator rationale and the choice of probes moved back to private controller evidence.

Fresh rubric-author trials exposed two further ambient-input failures before candidate generation. An audit-shaped assignment implicitly activated the installed Skill Auditor even though the author had been told not to inspect plugin source, and a separate author traversed a shared parent directory and imported lenses from another held-out target. The affected drafts were discarded. Explicit capability exclusions and one-target-only readable roots were required because a fresh conversation did not remove installed routing or shared filesystem state.

A subsequent twelve-run task trial named an absolute artifact destination while launching agents in separate host-owned projectless directories. Five results were absent from the declared artifact root; some had been written under the launcher's competing working directory and some could not be recovered from the evidence root at all. The round was rejected before grading. The correction was to make the assigned workspace the launcher's actual working root, not to copy outputs afterward or reinterpret a prompt path as custody.

A held-out auditor later delivered a contained relative symlink as the reproduction of a real source boundary defect. The custody helper rejected the entire artifact because its first implementation treated every link as an escape. That made a security control destroy legitimate evidence and would also exclude ordinary source trees that intentionally contain links. The helper was changed to preserve and hash relative links that remain inside the copied candidate tree while still rejecting absolute links, lexical escapes, symlinked custody ancestors, and special files. The failed anonymization became the integration case for the correction.

Another held-out audit round passed its executable fixture checks but failed semantically: the public maintainer brief implied that every host required both capabilities, while the target's own contract allowed a host to expose either one or both. The private oracle followed the target, and the rubric followed the contradictory brief. Auditors then surfaced the manufactured gap. The round was discarded before blind grading. Prompt purity therefore includes consistency with the authority the worker can actually see; hiding a different expected answer in controller state is not blinding.

A later eighteen-run audit comparison gave every executor an opaque workspace but prescribed one fixed output name in the host-global temporary directory. Concurrent auditors therefore shared mutable state; one run demonstrably read another condition's emitted index and its opaque workspace path. The entire round was rejected before anonymization. Fresh contexts and opaque workspace names do not establish independence while any executor-resolvable mutable namespace remains shared.

A later blind-review round exposed view transformation as another custody surface. Executor artifacts contained permission modes observed on read-only target copies, but the helper normalized non-executable files to mode `0600` in reviewer views. Reviewers then treated the different numeric modes as factual errors in the audits. The executable-bit conclusion happened to remain unchanged, but that does not make the comparison valid for packages whose full modes matter. Blind copies now preserve complete POSIX modes and continue to verify older executable-bit-only mappings for retained evidence. A view transformation must not silently alter a fact the decision may inspect.

Three later Skill Auditor runs exposed the opposite boundary: the probes existed, but two audits cited decisive files under disposable `work/` that were absent from the maintainer-facing artifact. The controller could reconstruct the runs, while the recipient could not resolve the cited paths. Evidence custody therefore includes the delivery boundary, not only experiment storage; a result is not retained handoff evidence until the artifact the user actually receives can resolve or reproduce it.

A later blinded review launch made the reviewer view read-only while the reviewer contract required writing `judgment.md` there. All three reviewers analyzed the candidates, but two host-captured final messages retained only a terse winner sentence rather than the requested grades, Notes, and comparative rationale. The attempts were not judgments merely because an output redirect produced a nonempty file. The launch was corrected and fresh reviewers were used. Output authority and the declared artifact interface are therefore part of custody, not incidental host configuration.

The nominal pre-exposure validator had received the worker payloads and rubric but not the exact reviewer prompt, published view paths, or effective sandbox authority. It therefore could not detect the path and output contradiction. Validation of selected source documents was falsely standing in for validation of the deployed evaluation interface. Subsequent gates include the composed reviewer view and launcher contract before any candidate result can influence their repair.

A later nine-review launch exposed capacity as part of that same interface. Nominal concurrency was available, but the shared temporary filesystem quota failed eight launches before a durable judgment was captured. After obsolete runtime-cache copies were removed, one unaffected observation was retained and only the eight infrastructure-failed observations were replaced in batches of three. The correction was not a larger retry allowance: evidence concurrency is bounded by the storage, runtime-state, trace, and artifact capacity that the deployed launcher can actually sustain.

A subsequent controller-side material copy exposed a more basic custody hazard before reviewer publication. A missing manifest filename left the computed source empty, turning a bounded copy into `/.`; the orphaned process placed roughly 3.4 GB of system files under one temporary review-material directory before termination. A follow-up diagnostic used zsh's special `path` parameter and thereby replaced `PATH` inside the loop. The contaminated helper-created tree was discarded and rebuilt from individually named, validated inputs. Evidence custody therefore also covers the controller's own path resolution: opacity and hashing after a copy cannot rescue a mutation whose source or target was not bounded before it began.

## Consequences

Treat parent intervention, retries, rescue, shared state, and readable sibling traffic as condition changes. Exclude, replace, or qualify affected evidence instead of repairing it retroactively. A fresh process or worktree is not automatically read isolation; use permissions, sandboxes, separate users, or another boundary when the threat requires it.

Resolve ambient mutable state to condition-local storage or an equivalent namespace before concurrent execution. A fixed shared temporary name is part of the experimental condition even when the task calls it disposable.

Preserve candidate and review-material facts through anonymization, including content, topology, contained link targets, and complete permission modes. If a necessary transformation changes a fact that reviewers could use, make the transformed view and its limitation explicit rather than calling it an equivalent blind copy.

Keep decision-changing probes beneath the delivered evidence root or make them reproducible from the delivered artifact. Do not cite controller-only or disposable paths as if a maintainer can inspect them.

Ensure the subject can actually satisfy the output contract in its assigned sandbox. A host-owned fallback transcript is not equivalent to a requested committed artifact when the failure changes its content or durability.

Treat shared capacity failures as harness observations, not candidate losses. Preserve them and replace affected runs only after the resource boundary is corrected; do not regenerate successful conditions or choose replacements from substantive output quality.

Resolve and validate every source and destination that can cause a broad controller mutation before starting it, and reject empty, root, unresolved, or unexpectedly broad paths. This ordering is binding because validation after the mutation cannot prevent filesystem or evidence contamination. Avoid shell names with interpreter-defined behavior in custody code.

Reopen only the affected causal claim when isolation or host behavior changes. Do not require blind machinery when identity cannot influence a purely mechanical check.
