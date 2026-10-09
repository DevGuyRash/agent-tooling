# Difficult Failures

Read this reference when a normal focused reproducer cannot faithfully expose the failure.

## Intermittent failures

Preserve a stable failure signature: assertion, error class, affected request, state transition, or trace span. Compare occurrence against time, load, order, seed, host, dependency version, and shared state. Increase repetition only when it preserves the production-relevant conditions and has a bounded stop.

Define the exposure unit before interpreting a clean run: one request, one lifecycle, one contested schedule, one failover, or another opportunity for the defect. Report attempted exposures and detection limits; a lower observed rate is not equivalent to absence.

Replace timing sleeps in a reproducer with observable conditions when possible. A timeout may bound the test, but elapsed time alone rarely identifies which condition failed to arrive.

## Concurrency failures

Separate ordering, visibility, atomicity, ownership, and resource-exhaustion hypotheses. Capture the synchronization events needed to distinguish them. Stress can improve reproduction probability, but it is not causal evidence by itself. Use deterministic scheduling, barriers, fixed seeds, tracing, or race detectors when the environment supports them.

Allow causes to be conjunctive. A defect can require a particular ordering plus resource pressure or a retry plus stale authority; do not force one component to be the sole root when removing either is necessary and the evidence supports the interaction.

Avoid adding locks or serialization until evidence identifies the violated invariant; a broad lock can hide the race while introducing latency or deadlock.

## Distributed failures

Trace one affected operation across boundaries using existing correlation identifiers. At each boundary compare:

- request or event identity and relevant payload shape;
- timeout, retry, cancellation, and deadline propagation;
- ordering, duplication, and idempotency assumptions;
- configuration and version observed by each component;
- authoritative state before and after the operation.

Prefer narrow structured observations over dumping entire environments. Redact tokens, credentials, personal data, and unrelated tenant or request content.

## Environment-specific failures

Build a difference table between failing and working environments. Include only dimensions that can affect the path: architecture, runtime and dependency versions, feature flags, locale, timezone, permissions, filesystem behavior, resource limits, network policy, and generated artifacts.

Test the smallest differing dimension first when its causal path is plausible. Do not make the environments identical wholesale; doing so destroys attribution.

## Build and CI failures

Distinguish source failure from stale artifacts, cache poisoning, dependency resolution, toolchain drift, missing secrets, permission differences, and resource limits. Re-run without a cache only when the cache is a live hypothesis, not as a universal first step.

For a test-order dependency, find a minimal preceding set or state mutation that causes the victim to fail. The durable fix restores isolation or makes the shared contract explicit; shuffling order alone is only a detector.

## Non-reproducible production failures

Do not claim a cause from correlation alone. State the confidence and competing explanations. Add bounded telemetry or a safe diagnostic path that can capture the next occurrence, with a removal or review condition. If the consequence is high, apply a reversible mitigation based on current evidence, kept separate from the fix.
