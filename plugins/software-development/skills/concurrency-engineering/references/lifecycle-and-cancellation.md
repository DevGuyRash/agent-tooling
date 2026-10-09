# Lifecycle and Cancellation

Load this reference for task ownership, cancellation, timeouts, callback registration, subprocesses, cleanup, or shutdown.

## Separate lifecycle states

Distinguish not admitted, admitted but not started, executing, cancellation requested, cleanup running, terminal, and outcome published when those states change safe behavior. Invocation can start work before a promise, future, or handle reaches a limiter; place admission at the real start seam.

An owner tracks every admitted operation until it is terminal or transfers ownership explicitly. Dropping a handle, returning from a timeout race, closing an observation stream, or seeing a direct child exit does not prove the underlying execution domain has stopped.

## Cancel through the operation contract

Check already-canceled input before forbidden acquisition or side effects when the API promises that boundary. Propagate the platform's existing cancellation channel and preserve its reason or status when contractual. Identify what actually unblocks the operation: a token, close, shutdown, signal, interrupt, queue closure, callback unregister, or supervisor action.

Issue the unblock action before joining when work cannot finish until that action occurs. Cancellation remains cooperative unless the selected platform proves stronger behavior. Escalate only through supported platform mechanisms and retain authority over the owned execution domain while doing so.

## Publish outcomes after cleanup

Record the winning terminal cause when the contract gives it precedence. Join operation cleanup separately, then publish the recorded result; do not let a later fulfillment or unrelated cleanup failure replace a cancellation, timeout, or primary execution failure accidentally. Retain secondary cleanup evidence through the repository's error, suppression, aggregation, or logging contract.

Remove timers, listeners, registrations, waiters, and owned resources once. Make late callbacks or duplicate terminal signals harmless. Do not destroy captured state until every execution path that can reach it is terminal.

## Subprocess and external work

Define argument and environment construction, spawn failure, stdout/stderr drainage or bounds, stdin closure, direct-child and descendant ownership, graceful termination, escalation, status collection, and drainer joins. Pipe EOF and leader exit are observation boundaries, not universal proof of descendant settlement.

For remote or durable effects that cannot be canceled, define reconciliation, idempotency, compensation, or ownership transfer rather than representing caller cancellation as rollback.
