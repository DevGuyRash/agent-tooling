# Test Selection

Read this reference only when the useful test boundary is unclear or a test could produce misleading confidence.

## Choose the boundary by the promise

| Promise to protect | Useful starting boundary |
| --- | --- |
| Pure transformation or local invariant | Unit or property test |
| Collaboration among owned components | Integration test |
| Published request, response, event, or library surface | Contract test |
| User-visible workflow across real boundaries | Focused end-to-end test |
| Existing behavior needed as a refactor or migration baseline | Characterization test |

Use the lowest-cost boundary that can fail for the promised outcome. A unit test is not automatically better: it is weak evidence when the failure can occur only through serialization, persistence, networking, framework wiring, or a public protocol. Conversely, avoid an end-to-end test when a smaller seam proves the same contract more precisely.

## Characterization is not a manufactured red

A characterization test records behavior that exists now. Run it before a behavior-preserving refactor or migration and expect it to pass. If current behavior is wrong and the expected correction is known, write a regression test for the desired outcome and observe the relevant failure.

Characterize only behavior that is declared, externally relied upon, or intentionally selected for the current change.

## Check discrimination

Before trusting a test, name a plausible production change that would make it fail. Briefly remove or invert the behavior, or otherwise prove the assertion observes the production path. Restore the code before continuing.

Use a counterexample that changes the promised behavior, not a test-only marker, injected function name, environment fingerprint, or mutation mechanism the test can detect directly. Run the test through the same authoritative entrypoint that normally protects the repository; a manually runnable file outside that selection is useful evidence only when its separate invocation is an explicit contract.

A passing test is weak evidence when it:

- never reaches production code;
- asserts only a mock's configured response or call sequence;
- can pass after the promised behavior is removed;
- shares the same faulty implementation with the code under test;
- depends on ordering, time, randomness, network, or global state accidentally.

## Use doubles deliberately

Prefer real owned collaborators when they are fast and deterministic. Use a fake, stub, spy, or mock when it controls a costly, dangerous, unavailable, or nondeterministic boundary, or when the interaction itself is the public contract. Preserve important semantics such as errors, retries, transactions, ordering, and side effects.

Avoid adding test-only behavior to production APIs. Keep test builders, fakes, fixtures, and clocks in test support unless they represent a genuine production abstraction.

## Match evidence to risk

Property tests help when many inputs share invariants. Contract tests help when producers and consumers evolve independently. End-to-end tests protect a few critical journeys, not every branch. Security, concurrency, persistence, and recovery behavior may require specialist tests beyond a normal red-green cycle.

When no reliable automated boundary exists, verify manually, then state what that covered and what remains unverified.
