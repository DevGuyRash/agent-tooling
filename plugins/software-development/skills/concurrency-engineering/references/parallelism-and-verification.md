# Parallelism and Verification

Load this reference for parallel algorithms, worker sizing, fairness, deterministic tests, races, or liveness evidence.

## Parallelize the critical path deliberately

Identify independent work, required ordering, shared resources, merge cost, and the real limiting resource. Dependent steps, tiny tasks, memory-bandwidth-bound loops, serialized downstream systems, and heavily contended state can lose throughput as workers are added, so the worker count within the shared bound comes from throughput measured against the serial path at several levels.

Preserve exact work accounting and result order when required. Define fail-fast, collect-all, partial-result, or retry behavior and ensure one failure cannot leave producers blocked or workers detached. Partition work so each task has enough useful work to amortize scheduling, synchronization, allocation, serialization, and merge overhead.

## Budget the system

Bound nested executors, task groups, connection pools, subprocesses, and downstream requests together. Avoid oversubscription and blocking operations on execution domains that require workers to make progress. Consider cache locality, false sharing, topology, and non-uniform memory placement only when representative profiles or scaling evidence make them live hypotheses.

## Test safety and liveness

Use deterministic barriers or controller-owned handshakes to hold a complete admitted cohort and prove maximum concurrency, ordering, and terminal completion. Test failure while submission is blocked, cancellation at each lifecycle boundary, early consumer exit, repeated shutdown, duplicate callbacks, and cleanup failure precedence.

Stress, randomized scheduling, race detectors, sanitizers, model checkers, and long-duration tests expand exposure but do not prove absence universally. Record runs, schedules, operations, seeds, duration, and supported platform. A test that compiles but never reaches its decisive assertion provides no behavioral evidence.

## Performance composition

When speed or scale is the objective, compare equivalent offered and completed work, queue state, latency distribution, worker scaling, resource ceilings, and shifted costs; parallel computation stays where that comparison shows it serves the target.
