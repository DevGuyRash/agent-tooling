---
name: software-foundation
description: "Use when writing, changing, reviewing, or revising code in any language: the design principles all code meets and existing code is brought to. Excludes questions, prose, and Git operations that touch no code."
---

# Software Foundation

Code that a change writes or rewrites meets these statements. A review names where the code under review departs from them. A revision brings the code it is asked to revise to them. The repository's conventions decide the form they take.

- Interfaces and behavior that callers, stored data, or other programs rely on, order, errors, and timing included, stay as they are unless the request changes them.
- Correct behavior, edge and failure cases included, outranks every statement below.
- Within a program, each rule or fact has one home.
- Code that needs a rule or fact uses its home instead of restating it, exporting the home or moving it to where every user can depend on it.
- Code that changes for the same reasons lives together.
- Code that looks alike but changes for different reasons stays separate.
- Dependencies between modules run one way, toward code that changes less often.
- An interface, generic, layer, pattern, option, or extension point serves a variation, substitution, or test seam that exists now.
- Tests check the behavior the request and the code's callers rely on, through the interfaces those callers use, at the level where that behavior can break, including across the boundaries it crosses.
- A test that fails while that behavior still holds, or that adds no evidence another test does not already give, is a defect to remove or rewrite.
- Data structures and algorithms fit the operations the code performs and the input sizes it will meet.
- Memory held at once grows with the input only where the operation needs all of it together.
- A failure is recovered from where the code can restore correct behavior, and otherwise reaches the caller with context naming the operation that failed.
- Everything code acquires or starts has one owner that releases it or observes it end on every path, failure and cancellation included.
- Calls to another system whose number grows with the input become batches where its interface accepts many items.
- Waits that neither use each other's results nor need their effects in a set order overlap instead of running one after another.
- Work in flight at once, counted across every level of fan-out, stays within the tightest limit it shares, such as a documented request limit, a connection pool, or memory.
- A deadline that the request states, a contract sets, or a caller passes in is enforced on the operation itself, so giving up on a wait also releases what it holds.
- An executor that must stay responsive, such as an event loop, hands blocking calls and long computation to the runtime's facility for them.
- Asynchronous code shortens waiting, not computation.
- Computation whose duration matters to its caller spreads across the cores available to it when it divides into parts that share no mutable state and dividing, coordinating, and combining them costs less than it saves; otherwise it runs on one core.
