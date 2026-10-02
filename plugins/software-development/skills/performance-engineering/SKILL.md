---
name: performance-engineering
description: "Use when new or existing code must reach, verify, or review a performance target or claim: latency, throughput, CPU, memory, I/O, or cost, with baselines, profiles, and benchmarks. Excludes slowdowns whose cause is unknown."
---

# Performance Engineering

This skill builds on the [Software Development Foundation](../../foundation.md).

Performance work toward a target or claim is falsifiable: define what should improve, measure a representative baseline, localize the limiting resource, and compare without silently spending correctness or another resource. A bare "make it faster" gets a decision-relevant criterion from product or operational evidence; a target whose tradeoffs belong to the user or system owner is theirs to set, not yours to invent. The foundation's statements apply without a baseline; measurement decides the claims made about a change and the tuning that goes beyond them.

Work toward a performance target or claim names the metric and unit (p99 latency, throughput, peak resident memory, allocations, artifact size, energy, cost per operation); the target or decision threshold; the workload's input distribution, concurrency, scale, and steady-state or cold-start conditions; the correctness, security, reliability, readability, and resource guardrails; and the environment and repository-native command for comparison.

- When load or queues change how much useful work is measured, count offered, admitted, completed, rejected, timed-out, and failed work.
- A target or claim is compared with the unchanged system under that workload, keeping raw results and enough environment metadata to reproduce the comparison, and repeating or interleaving runs when noise could change the decision.
- A profile of the representative workload, taken with the least-distorting tool and the counters the metric needs (CPU, allocation, heap, I/O, lock, scheduler, trace, system), attributes cost to a path and input, and optimization goes where that cost is; dead code is never optimized.
- An asymptotic improvement predicts scaling but is not runtime evidence; constant factors, cache behavior, allocation, vectorization, contention, and realistic input sizes can reverse it.
- One experiment at a time: state the bottleneck hypothesis and predicted metric effect; make the smallest change that tests it within the guardrails; keep benchmark and environment comparable to the baseline; accept a measurement only after confirming correctness and equivalent useful work; compare magnitude, variability, queue or concurrency state, limiting-resource utilization, and costs shifted to other resources; keep the change only if the evidence justifies its complexity and tradeoffs.
- Keep negative results as evidence; benchmarks do not replace correctness tests.
- Re-profile after a meaningful win, since the bottleneck may move; stop at the target, or when uncertainty exceeds the apparent gain or further cost is unjustified.
- Evidence matches the claim and reaches no further: end-to-end or workload benchmarks for user-visible latency and throughput; microbenchmarks only to isolate a known hot operation, never to stand in for the product; latency distributions for tail-sensitive systems, where an average can hide the regression; memory, I/O, cost, or energy deltas when resources can trade off; scaling runs at relevant sizes for complexity or capacity claims.

Read [measurement validity](references/measurement-validity.md) before designing a new benchmark, comparing noisy results, measuring JIT or managed runtimes, or turning a microbenchmark into a system-level claim; [complexity and data structures](references/complexity-and-data-structures.md) when the result depends on input growth, repeated passes, allocation shape, or choosing a data structure or algorithm; [load, parallelism, and resources](references/load-parallelism-and-resources.md) for queues, tail latency, async or parallel execution, worker counts, contention, topology, or a CPU, memory, storage, filesystem, or network ceiling; [optimization mechanics](references/optimization-mechanics.md) only after evidence localizes cost and the work needs language-neutral candidate mechanisms.
