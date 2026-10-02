"""The time limit of the fan-out checks (async-fanout-py, async-fanout-go, revise-fanout-py, revise-fanout-ts): a
client reads every endpoint of a service that allows LIMIT requests in progress, inside a ticket's budget.

The ticket's budget is what production enforces (a health check or monitor kills the command at that second),
whatever state the service is in, so each case is held to the budget itself plus only what this host adds to a
correct client's time, measured in the same check. A limit written as a multiple of a reference run's time
(five times the best of a few runs) is lenient exactly when the host is slow: under load the multiple rises
well above the budget, and a client that is only partly bounded, and would still be killed in production,
passes. The model here has no multiple:

- ideal_seconds: the time a correct client (LIMIT slots, each taking the next endpoint in ID order the moment
  it is free) spends waiting on the service alone, from the case's own latencies; what a host adds is on top.
- calibrate: runs the reference client (a correct one at the documented limit) until its best time is within
  SLOWDOWN_OK times that ideal, up to REF_TRIES runs, so a passing load spike does not decide the run; when even
  its best time is more than SLOWDOWN_MAX times the ideal the host is too loaded to judge timing and the run is
  invalid (ni.Unavailable), not failed.
- host_slack: the reference's best time beyond its ideal, which is what the host added just now. A check's time
  limit is its budget plus this slack, for every case it times, so the slack never exceeds
  (SLOWDOWN_MAX - 1) times the ideal.
- bound_limits: asserted as a check loads, that the largest limit the check can set stays below the least a
  client taking one endpoint at a time needs on any dataset (its floor: the sum of the answering endpoints'
  latencies, which the service sleeps, plus the slowest answering one's for each that must be reported as not
  answering), so no load lets a sequential client under the limit.

The limit is additive, so a client whose own waiting adds up to more than the budget (a pool of 2 or 3, batches
that each wait for their slowest endpoint) cannot pass on a loaded host that a multiple would stretch; the cost
is that a client within a second or two of the budget is judged by the host's load.
"""
import heapq

import no_interpreter as ni

SLOWDOWN_OK = 1.25  # calibration stops once the reference's best time is within this many times its ideal time
SLOWDOWN_MAX = 1.5  # beyond this many times its ideal time, even the reference's best time, the run is invalid
REF_TRIES = 3       # reference runs at most, the best of which measures the host's slowdown


def ideal_seconds(waits, slots):
    """The seconds a client keeping `slots` requests in progress spends waiting on the service alone, each slot
    taking the next of `waits` (the seconds each endpoint keeps a slot busy, in the order the endpoints are
    taken) the moment it is free."""
    free = [0.0] * slots
    for wait in waits:
        heapq.heappush(free, heapq.heappop(free) + wait)
    return max(free)


def bound_limits(budget, ideal, floors, slowdown_max=SLOWDOWN_MAX):
    """Raises AssertionError unless the largest time limit the check can set (the budget plus at most
    slowdown_max - 1 times `ideal`) is below every one of `floors`, the least a client reading one endpoint at a
    time needs on each dataset the check times."""
    ceiling = budget + (slowdown_max - 1) * ideal
    if not ceiling < min(floors):
        raise AssertionError(f"a time limit of up to {ceiling:.1f}s reaches the {min(floors):.1f}s a client reading "
                             f"one endpoint at a time needs")


def host_slack(times, ideal):
    """What the host added to a correct client's time: the best of `times` beyond `ideal`, never negative."""
    return max(0.0, min(times) - ideal)


def calibrate(drive, wrong, ideal, service, tries=REF_TRIES, ok=SLOWDOWN_OK, limit=SLOWDOWN_MAX):
    """Up to `tries` runs of the reference client (drive(i) -> its run, a dict with elapsed, rc, stderr, and server),
    stopping once the best time is within `ok` times `ideal`; the runs. Raises RuntimeError when the reference
    itself goes wrong (wrong(run) is true), and ni.Unavailable, so the run is invalid, when even its best time
    is more than `limit` times `ideal`. `service` names what it waits on, for the message."""
    times, refs = [], []
    for i in range(tries):
        ref = drive(i)
        refs.append(ref)
        if wrong(ref):
            server = ref["server"] or {}
            raise RuntimeError(f"the reference client went wrong (rc={ref['rc']}, refused {server.get('refused')}, "
                               f"held {server.get('held')}); the driver or host is broken: {ref['stderr'][-300:]!r}")
        times.append(ref["elapsed"])
        if min(times) <= ok * ideal:
            break
    if min(times) > limit * ideal:
        raise ni.Unavailable(f"host too loaded to judge timing: the reference's best of {len(times)} runs took "
                             f"{min(times)}s, more than {limit:g} times the {ideal:.2f}s it spends waiting on the "
                             f"{service}")
    return refs
