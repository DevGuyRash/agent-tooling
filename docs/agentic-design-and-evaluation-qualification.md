# Agentic Design & Evaluation 1.1.0 qualification

This record describes the evidence and limits for [release commit e64fb58](https://github.com/DevGuyRash/agent-tooling/commit/e64fb5825e498208f1eb5e6af580f544fc0efba0). The [package guide](../plugins/agentic-design-and-evaluation/README.md) owns current installation requirements, skill responsibilities, and public resource interfaces. The four entries share knowledge within a complete plugin so callers can use each capability directly without duplicating the foundation or requiring an automatic workflow. Split Testing owns comparative methodology; Friction Diagnostics remains separate.

## Mechanical checks

The release passed 82 reporter tests, 14 package/wrapper/profile tests, 29 converter tests, 37 installer tests, and six explicitly enabled native CLI/profile checks. Profile checks overlap between groups, so these counts must not be added as independent observations. [Release CI](https://github.com/DevGuyRash/agent-tooling/actions/runs/35071930828) and the [sensitive scan](https://github.com/DevGuyRash/agent-tooling/actions/runs/35071930895) passed.

Regression cases distinguish different decoded Unicode strings from equivalent JSON encodings, changed from unchanged symlink targets, and a regular file named `scripts` from a scripts directory. They also cover control-character paths, equivalent pretty/minified catalogs, and rejection of failed or malformed collection output.

Both host roundtrips and converted-package validators passed. Package tests resolve declared resources from actual converted output with the temporary source checkout removed, run commands from an unrelated working directory, and check containment, content preservation, notices, and executable permissions. These are structural and executable-interface checks, not evidence of model behavior.

The ancillary Skill Creator helper used in this qualification rejected the standard `compatibility` field because its local whitelist omitted it. The required dependency metadata was retained; that helper result is distinct from native host acceptance.

## Behavioral checks

Six fresh temporary ChatGPT chats received the complete frozen candidate and their original task materials. Assessment used original requirements, source artifacts, independently reproduced facts, and observed outputs. The candidate skills did not grade themselves.

| Task | Observed result |
| --- | --- |
| Narrow prompt edit | Made exactly the requested audience substitution without adding a workflow. |
| Execution-plan assessment | Preserved PostgreSQL and access controls, rejected invented implementation mandates and a finding quota, and identified incomplete overdue-selection verification. |
| Plugin audit | Detected a false standalone promise and stale navigation, accepted legitimate shared resources in a complete plugin, and preserved an applicable pinned method, version, and date. |
| Non-AI comparison | Selected the program earning 90 over the program earning 75 under the supplied scheduling rules; input hashes and outputs matched independent executions. |
| Misleading handoff and completed action | Reconstructed the original $50 cap, rejected the coordinator's assumed increase and mandatory method, and preserved the already-completed acknowledgment. |
| Unavailable originals | Produced provisional work, preserved the available source documents, and left unsupported decisions and action status unresolved. |

The audit's proposed standalone repair left an unused source-policy file without fully specifying its cleanup or ownership. A repaired section pointer does not demonstrate future navigation resilience. The handoff trial used synthetic records rather than a live external service. Captures and authored logs do not independently authenticate every claimed historical command.

The browser showed `6 Pro` with Latest selected and Personalized enabled. Exact backend identity, complete ambient isolation, native Codex/Claude model behavior, and reliable implicit selection were not established. These observations support the named task outcomes, not general superiority, a required reading path, or long-horizon effectiveness.

After the browser candidate was frozen, the collector and its regression changed to distinguish a file named `scripts` from a directory. All instruction and UI files remained identical to those in the release. Final mechanical checks cover the corrected code; the browser trials did not exercise that condition.

## Delivery boundary

The canonical marketplace update through `scripts/install-all --include agentic-design-and-evaluation` produced enabled 1.1.0 installations on Codex and Claude. All 41 package files and executable availability matched the published source in both caches. Claude's strict installed-package validation passed, and fresh Codex input exposed all four descriptions and the selected cache path. Saved comparisons preserved unrelated installations and host configuration. A subsequent selected install reported that all selected plugins were current.

Installation, catalog exposure, structural preservation, and browser task behavior are separate observations. Existing sessions can retain earlier instructions. Raw task captures and workstation inventories are maintainer records retained outside the published documentation; they are not runtime dependencies.

## Scoped compatibility evidence

A parser check recorded on 2026-08-17 against [Codex revision c6058cc](https://github.com/openai/codex/blob/c6058ccaa91ab17159cf805bf4d6d4edd87fe5fc/codex-rs/core-plugins/src/manifest.rs#L482-L536) found that raw `interface.defaultPrompt` accepted a string or a list. An array-shaped normalized representation did not establish rejection of a string input. This observation is scoped to the cited consumer revision, not a current publication guarantee; check the intended consumer when its revision or ingestion boundary changes.
