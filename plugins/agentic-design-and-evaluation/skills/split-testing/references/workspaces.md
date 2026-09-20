# Participant Workspaces

The [workspace preparation helper](../scripts/prepare_workspaces.py) copies caller-selected inputs into fresh participant directories and assigns output locations. It requires Python 3 and uses only the standard library. The orchestrator chooses the roles, counts, inputs, rounds, approval rules, and stopping conditions. The helper makes no model calls and performs no scoring, voting, adjudication, or stage advancement.

The orchestrator SHALL supply a new controller batch root beneath the repository's ignored local context directory. Its parent must already exist. The retained archive lives there; participant working directories live under a separately owned root in system temporary storage. The helper uses Python's `tempfile.gettempdir()`, which honors the host's temporary-directory configuration, including `TMPDIR` where supported. It treats the explicit controller path as its filesystem contract; it does not discover repositories, inspect Git ignore rules, or establish authority over the selected sources. Use a fresh controller batch root for each later group or round beneath the same experiment directory.

## Command and Batch Specification

Resolve `<skills-file-root>` to the directory containing this skill's `SKILL.md`; it is a descriptive placeholder, not a shell variable. For an experiment already prepared under `/repo/.local/context/comparison`, the command is:

```sh
python3 "<skills-file-root>/scripts/prepare_workspaces.py" \
  --run-root /repo/.local/context/comparison/batch-01 \
  --spec /repo/.local/context/comparison/batch-01.json
```

The UTF-8 JSON specification contains exactly `inputs` and `groups`. The numbers, labels, selections, and output names below illustrate caller choices; they do not define workflow roles or a required allocation:

```json
{
  "inputs": {
    "request": {
      "source": "/repo/fixtures/request.md",
      "destination": "request.md"
    },
    "candidate": {
      "source": "/repo/candidates/package-a",
      "destination": "candidate"
    }
  },
  "groups": [
    {
      "id": "group-a",
      "count": 2,
      "inputs": ["request", "candidate"],
      "outputs": ["response.md", "artifacts"]
    },
    {
      "id": "group-b",
      "count": 1,
      "inputs": ["request"],
      "outputs": ["findings.md"]
    }
  ]
}
```

Each input declares exactly `source` and `destination`. Sources may be files or directories; relative source paths resolve beside the specification file. Each group declares exactly `id`, `count`, `inputs`, and `outputs`. A count of one represents an individual assignment. Group IDs must be unique. Group and input IDs accept 1–64 letters, digits, underscores, and hyphens, beginning with a letter or digit. Counts must be positive integers. An explicit empty input selection is allowed; each group must declare at least one expected output path. Unknown fields, duplicate JSON keys, repeated selections, and missing sources are errors.

Input destinations are relative to each participant's `inputs/`; expected outputs are relative to its `outputs/`. These paths use `/`, cannot be absolute, and cannot contain backslashes, colons, control characters, empty components, `.` or `..`. Input destinations selected for the same group cannot overlap. The schema, source existence, and input inventories are checked before the helper claims the controller run root. Only the inputs selected for each participant are copied into its temporary workspace; copied link resolution is checked there before preparation can become ready.

Expected outputs are locations for the actual result, which can be free-form Markdown, native artifacts, or directories of artifacts. The helper creates the parent `outputs/` directory, but creates no expected result files or artifact directories. It does not generate semantic report templates or validate the eventual result. The orchestrator SHALL inspect the native outputs and preserve missing or incomplete results as such before relying on them.

## Resource Relationships

A selected directory includes all its contents. You SHOULD select a complete package when its entry relies on sibling references, scripts, or assets, or choose multiple destinations that preserve the needed relative layout. The helper does not infer dependencies from prose or code. A smaller input copy is useful only if it retains the legitimate sources and runtime support the participant needs.

Source roots must be declared using their canonical paths, without symlink components. Internal relative symlinks are preserved only when their targets are also selected for that participant and resolve to the same resource under the copied layout. An explicitly selected second input can supply the target of such a link. Absolute, broken, cyclic, escaping, or retargeted links are rejected. Materialize a suitable input copy when its links cannot meet this contract; do not silently broaden a participant's access. Filesystem support and permission to create symlinks are required when selected inputs use them.

The helper checks link resolution in the actual copied filesystem, including links followed before a later `..` component. It requires the resolved endpoint to remain inside that participant's input tree and to correspond to the intended selected source. Comparing original source endpoints or lexically simplifying the link text does not establish those properties.

The helper copies regular files and directories, preserves regular file permission bits, and rejects special files such as sockets and FIFOs. Directory permissions are private to the creating user where supported. Inputs must remain stable during preparation. Metadata checks detect source changes during copying, but this is not an atomic source snapshot or protection against another process modifying the filesystem. Neither the controller run root nor the temporary workspace root can be inside a selected directory source; prepare a suitable source snapshot when selecting a larger tree would otherwise include the preparation itself.

## Returned Locations and Controller Record

Successful preparation prints one compact JSON line with `preparation_status`, `run_root`, `archive`, `temporary_root`, `manifest`, and `participants`. Each participant has an opaque `id`, its caller-selected `group`, `workspace`, selected `inputs` mapped to absolute paths, `output_root`, absolute `expected_outputs`, and a controller-owned `retained_outputs` directory. Its `host_agent_id` starts as `null`. Use `--summary-only` to print the participant count and controller/temporary locations while leaving participant details in the manifest. Use `--help` for command options.

The layout is:

```text
/repo/.local/context/comparison/batch-01/
  archive/
    manifest.json
    retained/<participant-id>/

<system-temporary-directory>/split-testing-<unique-id>/
  participants/<participant-id>/
    inputs/<selected-destinations>
    outputs/
```

The controller manifest retains the specification, preparation status, boundary record, and participant locations. It is controller material: passing it or the full command output to a blind participant can expose other assignments or source identities. The orchestrator SHALL dispatch each participant with only the legitimate task, authoritative inputs or access, assigned output locations, and applicable effect boundaries. The actual task can require additional material; the batch schema does not replace a role-complete assignment. See [Information and Execution](information-and-execution.md) for the delegation and exposure contract.

The orchestrator SHALL register actual host agent IDs against participant IDs, retain the native responses and artifacts in the archive, and manage cleanup. The helper neither dispatches agents nor waits for, collects, or judges their work. Its `prepared` flags and `preparation_status: "ready"` concern only filesystem preparation. They do not mean the participants have run, supplied their expected outputs, or satisfied an approval rule.

## Isolation and Access Boundaries

The default arrangement is instructed separation: fresh contexts where supported, scoped input copies, assigned output directories, and explicit access boundaries. The orchestrator SHALL inspect the host's actual inheritance, tools, mounted files, and permissions, apply available host restrictions when appropriate, and record which boundaries were enforced and which relied on agent compliance. A fresh context or a private-looking directory name alone does not establish blindness or isolation.

The manifest separates `preparation_enforced` controls from `host_enforced` restrictions, `requires_agent_compliance` boundaries, and `not_verified` conditions. The helper initially records no host restrictions. The orchestrator SHALL add the actual host enforcement and its evidence when configuring dispatch; remaining limits stay explicit. The helper cannot restrict another agent running as the same user from reading sibling inputs, the original repository, or the controller archive. Its directory permissions protect against other operating-system users only where the host honors those permissions. Directory creation SHALL NOT be reported as sandbox enforcement.

## Failure, Recovery, and Cleanup

The helper reserves the controller root and the separately named system temporary root exclusively; an existing directory, file, or symlink is refused without replacement. Different fresh batches can be prepared concurrently. Concurrent invocations targeting the same controller root have at most one successful owner. There is no resume or overwrite mode, and the helper does not reuse a prior participant directory.

The controller manifest records the planned `temporary_root` before its exclusive creation and sets `temporary_root_created` after confirming ownership. A stop during that allocation can leave a recorded path without confirmed ownership; the orchestrator SHALL inspect such a path before deciding what it can safely remove. A planned path alone is not permission to delete pre-existing or unrelated content. Once created, the manifest identifies the temporary tree even when abrupt termination prevents normal cleanup.

The orchestrator SHALL check the manifest before dispatching from a batch. A completed preparation has `preparation_status: "ready"`, published by replacing the manifest only after all participants are prepared. A live or interrupted preparation can have `preparing`, `failed`, `interrupted`, a missing manifest, or an unreadable manifest. None of those states establishes a usable batch. The orchestrator SHALL determine whether preparation is still running before recovering or deleting its files.

| Observation | Recovery |
| --- | --- |
| Validation fails before claiming the run root | Correct the specification or paths and retry. No new batch was created. |
| Temporary allocation, copying, or copied-link validation fails, or a handled interrupt occurs | The helper removes the temporary root it owns where the filesystem permits and retains the controller manifest with a non-ready status. Inspect the failure, correct its cause, and use a fresh controller root. Existing unowned paths are preserved. |
| Abrupt termination leaves `preparing` or no readable manifest | After confirming the process stopped, preserve any evidence needed to diagnose the partial attempt and inspect the recorded temporary location and ownership. Clean up only the owned temporary tree and controller batch. Prepare a fresh root. |
| The ready manifest was committed but stdout was lost or interrupted | Recover participant locations from the ready manifest. Do not create duplicate dispatches by assuming preparation failed. |
| A completed participant lacks an expected output | Preserve the native response and missingness in the controller archive. Decide whether continuation or replacement is warranted; preparation does not turn an absent result into success. |

Ordinary errors print short `error:` and `hint:` lines to stderr and exit nonzero; successful stdout is JSON. A handled interrupt normally exits 130; unusable input or preparation failure exits 2. An abrupt operating-system termination may use its native status. The failure record reports `partial_workspaces_removed` and, when cleanup fails, `cleanup_failure`. When filesystem failure also prevents updating that record, an absent or non-ready manifest still leaves preparation incomplete.

After successful preparation, workspace ownership passes to the orchestrator for the participant lifetime. The orchestrator SHALL copy the completed native outputs and condition evidence needed for the comparison into the retained archive before deleting the temporary tree, and SHALL preserve the archive while it remains needed. System temporary storage supplies working space, not durable evidence retention. Cleanup is limited to the paths owned by that batch; the helper does not sweep stale siblings or remove earlier experiments.

## Native File Tool Fallback

When Python is unavailable, the orchestrator MAY prepare equivalent workspaces with native file tools. It SHALL use a newly owned controller batch root under the ignored context directory and separate participant directories in system temporary storage, copy only the assigned inputs while preserving required relationships, provide separate output locations without fabricated results, and keep a controller record of participant IDs, host IDs, locations, expectations, and actual boundaries. It SHALL refuse accidental replacement and validate link resolution in the copied layout, rejecting escapes, cycles, missing targets, or retargeting. It SHALL keep partial preparation distinguishable from a complete batch and retain completed outputs before cleaning up temporary directories. Python installation is not a prerequisite for using Split Testing's broader evidence and delegation guidance.
