# Load, Parallelism, and Resource Ceilings

Read this reference when queues, concurrency, tail latency, scaling, topology, or system resources can change the performance conclusion.

## Preserve offered work

Distinguish work offered by the driver from work admitted, started, completed successfully, rejected, canceled, timed out, or failed. An apparent latency or throughput win is invalid when the candidate silently drops, delays outside the timed region, coalesces incorrectly, or sheds more work than the baseline.

Define the population behind every statistic. A success-conditioned latency distribution is not offered-work latency and must not be presented as the whole system when failures or timeouts differ. Preserve caller-observed latency for terminal outcomes when that metric is defined; for work rejected before a latency exists, report loss separately and make the performance decision fail or remain undefined when its loss/error guardrail is exceeded. Do not fabricate tiny or sentinel latencies for dropped work, and do not let deleting the slowest outcomes make a latency objective appear healthier.

Name the load model. A closed loop waits for each response and can hide overload through coordinated omission; an open or externally paced model can expose queue growth but needs an explicit overload and shedding contract. Record arrival rate, concurrency, queue depth or wait, service time, and completion rate at the decision-relevant scale.

Exercise boundary and interior configurations that can change arithmetic width, overflow, algorithmic work, queue state, or loss behavior. Use checked or sufficiently wide accounting for counts, time, bytes, rates, and percentile indexes. When a compact model or simulator supports the conclusion, compare representative cases with a simpler independent reference rather than only testing examples produced by the same implementation.

## Explain tails and queueing

Separate time waiting for admission, locks, workers, I/O, and downstream capacity from active service time. Compare distributions and sample counts, not only averages. Correlate tails with queue length, pauses, retries, cold paths, skew, or resource saturation before changing code.

## Scale parallel work deliberately

Within the shared bound, choose a target's worker level by measuring a serial or low-concurrency reference and several supported levels. Stop increasing parallelism when throughput flattens, tail latency or failure rises, or another resource becomes the ceiling. Budget nested pools, async tasks, subprocesses, database connections, and downstream quotas together; moving waiting work into more tasks does not create capacity downstream.

Parallel work needs an ownership contract as well as a worker count: bound admission, account for every accepted operation, propagate the selected failure or cancellation policy, unblock waiters, and join owned execution before releasing dependent resources. Measure coordination, scheduling, serialization, and merge costs alongside useful work.

## Locate resource ceilings

Use counters appropriate to the environment to distinguish CPU execution, memory bandwidth or capacity, allocation and collection, storage latency or throughput, filesystem metadata, network bandwidth or round trips, lock contention, and downstream service limits. A ceiling outside the changed component can make local optimization irrelevant or merely shift waiting elsewhere.

For CPU and memory work, consider cache locality, branch behavior, vectorization, false sharing, synchronization, and non-uniform memory placement only when the workload and available evidence make them plausible. For I/O, distinguish request count, byte volume, batching, queue depth, cache effects, flush or durability requirements, and remote round trips.

## Match the claim

Report the range actually exercised and the first observed ceiling. Do not extrapolate a straight line beyond the measured topology or resource budget. When the candidate changes load shedding, batching, durability, ordering, or consistency, treat that as a contract change unless the guardrail permits it.
