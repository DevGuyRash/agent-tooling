# Concurrency and Process Lifecycles

Read this reference in addition to the selected dialect reference when work starts background jobs, runs units concurrently, manages timeouts or cancellation, or owns a subprocess tree.

## Decide whether parallel work belongs

Parallelize independent work only when overlap is likely to improve the user-visible constraint, such as latency or throughput, after accounting for startup, scheduling, coordination, and contention. Preserve a sequential path when the workload is small, order-dependent, rate-limited, or dominated by a shared bottleneck.

Concurrency changes observable behavior. Define the maximum aggregate concurrency, admission and backpressure policy, output ordering, acceptable nondeterminism, timeout scope, retry policy, and whether one failure stops admission, cancels peers, or drains already-admitted work.

## Own every admitted unit

Retain an identity or handle for every admitted job, task, or process and associate it with its input. Do not launch fire-and-forget work from a script whose completion is meant to report the operation's result.

Before returning, settle every admitted unit and, inside each unit, the work it starts: observe its terminal status, collect bounded output, and reap or dispose its handle. Keep the primary failure or interruption distinct from cleanup failures; report secondary failures without replacing the status callers rely on.

If failing fast, stop new admission first, signal or cancel only owned work, drain required streams, wait for termination, clean up owned resources, then return the selected failure. Make teardown idempotent because normal completion, traps, `finally`, and cancellation can converge on it.

## Bound pressure and output

Use one aggregate concurrency budget across nested pools, jobs, and child scripts. A per-loop throttle is not an aggregate bound when several loops or outer jobs run simultaneously. Bound queued input and captured output as well as active workers; otherwise concurrency merely moves the resource failure.

Concurrent writes can interleave or reorder stdout, stderr, and PowerShell streams. When ordering or record integrity is part of the interface, capture per-unit output within a limit and merge it deterministically at the declared boundary. Drain child pipes while processes run so full buffers cannot deadlock them.

Do not share mutable files, shell variables, PowerShell objects, current-directory state, or temporary paths across workers unless the mechanism and synchronization are deliberate. Prefer isolated per-unit state and an explicit reduction step.

## Match cancellation to the execution domain

A shell job, direct child PID, process group, descendant tree, PowerShell job, runspace, remote job, and native process are different ownership domains. Killing or stopping one handle does not universally terminate everything it started. Use platform and interpreter mechanisms whose closure matches the declared contract; otherwise state the residual and verify that no orphaned work survives.

Do not assume interactive job control exists in automation. Do not signal a broad process group, enumerate unrelated jobs, or remove session-wide jobs unless the invocation is isolated and that authority is explicit.

## Verify the lifecycle

Test the sequential edge, the concurrency limit under load, mixed fast and slow units, one and several failures, timeout during admission and during execution, interruption while waiting, bounded output, deterministic merge behavior when promised, and cleanup after partial startup. Verify every admitted unit, and anything it started, reaches an observed terminal state and no owned child, job, temporary resource, or lock remains.
