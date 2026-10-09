# Optimization Mechanics

Read this reference only after measurement localizes a meaningful cost.

## Remove or avoid work

First check whether the expensive operation, repeated traversal, conversion, allocation, serialization, copy, query, syscall, network round trip, or recomputation is required for the promised result. Reuse or cache only when the key includes every result-changing input and invalidation, memory growth, staleness, and concurrency are acceptable.

## Improve data movement

Reduce unnecessary materialization and copying; stream or process incrementally when ownership and error semantics allow it. Choose representations that improve locality and useful density without losing alignment, precision, lifetime, or interoperability contracts. Batch fixed overhead only within latency, memory, ordering, and partial-failure guardrails.

## Use concurrency for the actual bottleneck

Overlapping independent waits shortens them only while the downstream system has spare capacity. Parallel execution speeds up independent CPU work large enough that coordination and memory traffic do not dominate it. Dependent work on the critical path stays sequential, since parallelism cannot shorten it. Bound all fan-out, and measure useful scaling at each concurrency level tried.

## Specialize only with evidence

Compiler optimization, vectorization, preallocation, pooling, custom allocators, branch reduction, lock partitioning, zero-copy APIs, compression, and platform-specific paths can help a localized cost. Each can also increase memory, retention, code size, contention, latency variance, portability risk, or maintenance cost. Test the smallest mechanism that isolates the hypothesis and retain a clear fallback when the optimized path has a narrower validity domain.

## Preserve the whole operation

Include setup, teardown, conversion, synchronization, retries, cleanup, and output consumption when the real caller pays them. Re-measure at the caller-visible boundary after a local win and re-profile to find the new limiting path.
