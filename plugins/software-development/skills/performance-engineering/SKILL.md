---
name: performance-engineering
description: Use when latency, throughput, CPU, memory, allocation, I/O, scale, or cost is explicit. Requires measurement; exclude unknown-cause regressions and speculative tuning.
---

# Performance Engineering

This skill builds on the [Software Development Foundation](../../foundation.md).

Performance work is falsifiable: define what should improve, measure a representative baseline, localize the limiting resource, and compare without silently spending correctness or another resource. A bare "make it faster" gets a decision-relevant criterion from product or operational evidence; a target whose tradeoffs belong to the user or system owner is theirs to set, not yours to invent.

Before changing the implementation, fix the metric and unit (p99 latency, throughput, peak resident memory, allocations, artifact size, energy, cost per operation); the target or decision threshold; the workload's input distribution, concurrency, scale, and steady-state or cold-start conditions; the correctness, security, reliability, readability, and resource guardrails; and the environment and repository-native command for comparison.

- When load or queues change how much useful work is measured, count offered, admitted, completed, rejected, timed-out, and failed work.
- Baseline the unchanged system under that workload, keep raw results and enough environment metadata to reproduce the comparison, and repeat or interleave runs when noise could change the decision.
- Profile the representative workload with the least-distorting tool and the counters the metric needs (CPU, allocation, heap, I/O, lock, scheduler, trace, system), and attribute cost to a path and input before optimizing; never optimize dead code.
- An asymptotic improvement predicts scaling but is not runtime evidence; constant factors, cache behavior, allocation, vectorization, contention, and realistic input sizes can reverse it.
- One experiment at a time: state the bottleneck hypothesis and predicted metric effect; make the smallest change that tests it within the guardrails; keep benchmark and environment comparable to the baseline; accept a measurement only after confirming correctness and equivalent useful work; compare magnitude, variability, queue or concurrency state, limiting-resource utilization, and costs shifted to other resources; keep the change only if the evidence justifies its complexity and tradeoffs.
- Keep negative results as evidence; benchmarks do not replace correctness tests.
- Re-profile after a meaningful win, since the bottleneck may move; stop at the target, or when uncertainty exceeds the apparent gain or further cost is unjustified.
- Evidence matches the claim and reaches no further: end-to-end or workload benchmarks for user-visible latency and throughput; microbenchmarks only to isolate a known hot operation, never to stand in for the product; latency distributions for tail-sensitive systems, where an average can hide the regression; memory, I/O, cost, or energy deltas when resources can trade off; scaling runs at relevant sizes for complexity or capacity claims.

Read [measurement validity](references/measurement-validity.md) before designing a new benchmark, comparing noisy results, measuring JIT or managed runtimes, or turning a microbenchmark into a system-level claim; [complexity and data structures](references/complexity-and-data-structures.md) when the result depends on input growth, repeated passes, allocation shape, or choosing a data structure or algorithm; [load, parallelism, and resources](references/load-parallelism-and-resources.md) for queues, tail latency, async or parallel execution, worker counts, contention, topology, or a CPU, memory, storage, filesystem, or network ceiling; [optimization mechanics](references/optimization-mechanics.md) only after evidence localizes cost and the work needs language-neutral candidate mechanisms.
