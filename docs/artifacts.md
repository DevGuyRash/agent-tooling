# Artifact synchronization

`packaging/artifacts.toml` owns artifact declarations. `scripts/artifacts.py` provides the language-independent execution and publication interface. Task-specific programs own their transformations, including pinned Rust builds, Mermaid discovery and the browser-library build. Python 3.11+ and Git are required for the engine. Verification needs no producer toolchains; generation requires the selected task’s listed tools and their declared versions. The Python producers here use the standard library. Browser assets use the TypeScript version pinned in their `package.json`; Rust recipes pin the compiler, release helper and linker versions.

## Commands

| Command | Effect |
| --- | --- |
| `just bootstrap` | Enable contributor hooks, check receipts/outputs and report missing task build tools. |
| `just artifacts-sync` | Prepare and synchronize changed automatic tasks from the working tree. |
| `just artifacts-sync --task <id>` | Synchronize selected tasks and dependencies. Explicit tasks can be selected here. |
| `just artifacts-check` | Verify receipts and outputs without running producers or modifying files. |
| `python3 scripts/artifacts.py list` | List tasks, dependencies and delivery destinations. |
| `just mermaid-refresh` | Capture current official documentation, then generate both Mermaid references. Network access belongs to the explicit capture task. |
| `just visual-previews` | Assemble report examples under `.local/context/visual-library-previews/reports/`. |
| `just hooks-install` | Activate this repository’s pre-commit and pre-push hooks in the current clone. |

The CLI locates its repository independently of the invoking directory. `--repo <path>` selects another repository. `--source index` reads staged sources; `sync --source index --stage` publishes generated files into that selected index. `check --source commit:<revision>` checks a committed tree, including outgoing branches other than the checked-out branch. `--task` is repeatable. Commands return compact JSON and short actionable errors; producer stdout and stderr remain in the repository’s local context directory.

## Contributor setup

Run `just bootstrap` after cloning, or `python3 scripts/artifacts.py bootstrap` when `just` is unavailable. Git and Python 3.11+ are the setup prerequisites. Setup uses the shared task declarations, command environment and read-only artifact verifier. It enables both repository hooks and reports missing executables with the tasks that need them. Valid delivered artifacts remain usable without installing every producer toolchain. Repeated setup leaves current configuration and artifacts intact.

`--task <id>` selects a contribution area and its dependencies. `--require-tools` makes unavailable executables fail setup even when their artifacts are current. These are executable-availability checks; the maintained producers enforce actual pinned versions. `just rust-fetch` retains the explicit Rust dependency-fetch operation. Contributor setup runs no producers, network refreshes or dependency installations and does not stage files. Stale or edited artifacts produce a nonzero result with the normal synchronization recovery instruction; hook activation remains available to support subsequent commits.

The hook installer checks the `python3` used by the hooks, preserves custom hook selections and existing active native hook files, and reports any conflict. `--replace-hooks` explicitly switches the selection to `githooks` without deleting the previous hooks. When Git worktree-specific configuration is enabled, setup writes only the selected worktree’s setting; otherwise it uses repository-local configuration. Global settings remain unchanged. Missing or symlinked maintained hook files are refused before configuration changes.

CI calls verification directly and `just ci` uses `rust-fetch`, so CI does not activate contributor hooks as a side effect. Container-specific `scripts/setup.sh` and `scripts/maintenance.sh` retain their explicit Rust setup roles; they are separate from the contributor command.

## Define a task

```toml
version = 1
receipt_dir = "packaging/receipts"

[tasks.reference]
inputs = ["scripts/make_reference.py", "sources/reference.json"]
command = ["{python}", "scripts/make_reference.py", "--output", "_out/reference.md"]
[[tasks.reference.outputs]]
source = "_out/reference.md"
destinations = ["plugins/first/skills/example/references/reference.md", "plugins/second/skills/example/references/reference.md"]
```

A direct-copy task omits `command` and names a declared input as its output source. `directory = true` delivers all files beneath an output directory. `executable` optionally sets the delivered executable bit. A destination has exactly one owner, including directory descendants. Input globs respect path segments: `*` matches within one segment and `**` spans directories. Literal input directories include their descendants. `optional_inputs` allows absent sources; `exclude` removes selected input paths. Paths are repository-relative and symlinks must resolve within the materialized declared resources.

`needs = ["other-task"]` orders preparation. Declare the actual output paths consumed by a dependent task as its inputs. Its fingerprint follows those bytes: a parent rerun producing identical consumed content leaves the child current. Use `automatic = false` for explicit network refreshes and local demonstrations. `cache = false` runs a selected task every time; it is appropriate for explicit observation of upstream state. Automatic tasks must remain offline, including any behavior inside their commands. Producers run with ordinary host permissions; staging is an ownership and input boundary, not an operating-system sandbox.

Commands are argument arrays, executed without a shell in a private workspace containing declared inputs. `{python}`, `{root}`, `{output}` and `{task}` expand to the current interpreter, workspace, `_out` directory and task ID. `ARTIFACT_SOURCE_ROOT`, `ARTIFACT_OUTPUT_ROOT` and JSON `ARTIFACT_TASK_PARAMETERS` provide the same context to producers. `parameters` holds opaque task-specific settings. `tools` declares executable availability; it does not fingerprint arbitrary installed programs. Identity-bearing toolchain requirements belong in declared lock/configuration inputs or task parameters and must be checked by the producer. Changing those pins invalidates the task. `environment` supplies explicit command settings, and `timeout` bounds execution.

## Receipts and safe synchronization

A successful receipt records the effective individual task definition, each input path/hash/mode, and every output path/hash/mode. Added, removed and renamed input files change the fingerprint. Editing another task does not. Synchronization reuses only complete outputs whose identities match; missing artifacts are regenerated. Receipts and delivered artifacts are committed together. The engine keeps no required machine-local execution cache.

`sync --prepared <directory>` can restore outputs from a verified prepared artifact tree. The tree contains repository-relative delivered paths and matching receipts, either directly or beneath a single artifact-job subdirectory per task. The task declaration, inputs, fan-out coverage and output bytes must match. These content receipts establish consistency, not publisher authenticity; select a trusted artifact source. Existing packaging `sync-artifacts` and `compare-artifacts` commands use this same validation.

Manual output changes produce a conflict diagnostic. Preserve useful edits in the maintained source, then rerun. `sync --replace` authorizes replacing reviewed differences within the declared output ownership; it is an explicit repair option. Changing delivery ownership requires reviewing and removing the retired outputs and their old receipt together before regeneration. Task-specific `receipt` paths support ignored local previews. Public package outputs use the normal committed receipt directory.

The engine prepares all selected results before publication and checks inputs, reused outputs, directory membership and selected-index identity again. It publishes files and receipts through a recoverable transaction. Producer failure or handled interruption leaves accepted outputs intact. On interruption during publication, rerun the same command: a journal under the selected Git directory identifies the accepted side and restores consistency. Concurrent edits or an unrelated Git lock can prevent automatic recovery. Preserve those edits and the journal, finish the other Git operation, and retry. If the index or owned outputs changed after interruption, reconcile their changes against the journal’s before/after records before removing recovery state; the tool refuses to guess. It never requires discarding unrelated staging. Linux native Git fixtures exercise the transaction; equivalent native Windows qualification remains separate.

## Git and CI

Pre-commit reads the proposed commit, including partial staging and `GIT_INDEX_FILE`, and stages declared outputs with a controlled index transaction. Unstaged source changes remain unstaged. Conflicting unstaged output changes cause refusal. Current tasks need no compiler. A changed producer requiring an unavailable pinned tool fails with its recovery path; hooks do not install dependencies or fetch documentation. Amendments and linked worktrees use their selected indexes. When Git retains a second locked index, as in `git commit --only`, generation refuses before publication: stage the desired paths and use a regular commit. This preserves both proposed and retained staging. Existing prepared worktree outputs identical to the generated result can be staged automatically. Pre-push checks the outgoing revision IDs supplied by Git without generating or installing anything.

CI calls the same `check --source commit:HEAD` implementation. Local generation, Git automation and CI therefore share the task definitions, fingerprint rules and output checks. Host conversion and plugin installation consume prepared packages; these operations remain explicit. Retained execution logs, browser qualification and review evidence live outside shipped plugin documentation.

## Mermaid source and delivery

`packaging/sources/mermaid/upstream.json` captures the resolved official Git commit, discovered syntax pages, full page contents and navigation metadata. `mermaid_refresh` resolves the repository's current default branch and documentation homepage, then selects the source documentation tree using its site configuration when generated mirrors are also present. Markdown and MDX pages are discovered from the complete Git tree. Both catalog tasks regenerate offline from those captured bytes. Failed retrieval, incomplete capture or renderer metadata failure preserves the accepted references.

Descriptions prefer upstream metadata, then complete explanatory sentences from introductory prose or blockquotes; adjacent warnings and experimental notices remain separate source qualifications. Mermaid code fences supply documented starters. The bundled catalog observes their detection against the exact integrity-checked renderer, preserving ambiguous and unmatched entries. The broader catalog lists all captured documentation topics. Published navigation and page metadata supply documentation links, including a changed documentation hostname or base path. Discovered links are fetched and checked for a matching page before capture; unpublished topics use the repository's live `HEAD` source link. Every topic also retains its pinned captured-source link. Missing information stays visible. The catalog provides navigation for executor judgment; it does not prescribe diagram choices or counts.

Refresh requests have bounded response sizes, timeouts and retries for transient failures, including short server-directed backoffs. Truncated trees, ambiguous source roots, empty documents and incompatible registry responses stop generation with a concise diagnostic. An upstream change outside the supported discovery contracts can still require maintenance; the tool preserves accepted references instead of publishing a partial catalog. `just mermaid-refresh` is the explicit online operation; normal synchronization and Git hooks remain offline.

Split Testing ships the renderer and its exact-support reference. Visualization ships the broader reference and source links. Each package receives its own Markdown and license bytes through declared deliveries; neither depends on repository source snapshots at runtime.
