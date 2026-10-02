# Qualification: `async-fanout-py`

The person asks for a new `dockctl sweep` command in dockctl, an existing standard-library Python tool for a city bike-share (list and show commands, a gateway client on urllib with no timeouts, a fake gateway for its tests, a few commits of history). The sweep reads every dock's status (about 200), prints one line per dock in ID order as `show` prints it, reports docks with no answer within 2 seconds as offline and HTTP errors as failed, ends with a summary line, and exits 0, 1, or 2. It runs inside a 20-second health check. The gateway's documentation (`docs/gateway-api.md`) allows each client at most 16 requests in progress, answering 429 beyond that, counts a request until the response is sent or the client hangs up, and says the gateway waits up to 60 seconds on a dock that does not answer. The prompt states the budget and points at the documented limits; it names no technique.

A sequential sweep prints the right report and takes over 40 seconds. Starting every read at once, or sizing a pool from the CPU count, gets 429s past 16. Giving up on a read without closing its connection (`asyncio.wait_for` around a blocking read in a worker thread, or a thread joined with a timeout) leaves the gateway counting the request, so the client goes over the limit once enough docks fall silent, whatever its own cap; a client that only paces its reads has no bound at all. A client that keeps a silent dock's request open after giving up on it (a fixed pool of 16 workers whose worker stays blocked on the read while the sweep moves on and exits) never goes over the limit and exits on time on an ordinary day, but holds each such request until the gateway's own wait ends, so when more docks are silent than it has workers, the whole sweep waits on them.

## How the checks decide

Every case runs `python3 -m dockctl sweep` from a read-only copy of the agent's repository, with `DOCKCTL_GATEWAY` set, in its own bubblewrap sandbox: host read-only, home, `/tmp`, and `/run` hidden, its own network and PID namespaces. `hidden/driver.py` serves the gateway on 127.0.0.1 inside that network namespace. The dataset and expected report are made in `check.py` and reach the driver on standard input. After the command exits the driver keeps the gateway listening for 2 seconds, kills everything left in the sandbox, and only then prints its verdict.

The gateway counts a request from the moment its headers arrive until it starts sending the response, or until the client closes the connection. When a request arrives it first drops counted requests whose client has hung up, and before refusing one it keeps doing so for up to 50 ms, so a client that closes one connection and opens the next on another CPU is never counted for the old one. A request that is refused, or whose client hangs up, still counts as asked for. The driver also records how long each request stayed in progress while the command ran (up to its exit, when the kernel closes whatever it still holds), and counts as held every request in progress longer than 8 seconds: 4 times the ticket's 2 seconds, and past the latest answer of a late dock (5.5 s), so only a request on a silent dock that the client neither got an answer to nor hung up on can be held. A correct client's longest request, the reference client's included, was at most 2.16 s across these runs, at load averages up to 100.

The cases:

- Main: 203 docks. 187 answer in 60 to 260 ms; 5 slow ones answer in 1.0 to 1.2 s (within the ticket's 2 seconds, so a client with too short a timeout misreports them); 3 late ones answer only after 3.2 to 5.5 s (so offline by the ticket's rule); 4 offline ones the gateway holds for 60 s, then 504; 4 get 500 or 502. The list comes in no particular order. Offline docks are drawn from the first quarter of both the ID order and the list's order, so their 2 seconds run out while a client working through either order still has docks to read; slow, late, and failed docks from the first 60%, so no client ends on a long wait.
- All answering: 40 docks.
- Outage: 203 docks, 20 offline and 30 slow, all in the first third of both orders. More docks are silent than the gateway's limit, which separates the clients described above whatever their own cap.
- No gateway: exit 2 within 10 s.
- Existing commands: `list` and `show` run one after another against a small gateway, with the arguments, environment, and expected output the fixture's tests use.

A pool sized from the CPU count is judged alike on every host that decides: every command gets `PYTHON_CPU_COUNT=32`, which fixes `os.cpu_count()` and `os.process_cpu_count()` on Python 3.13 and later, and the run is invalid (not failed) when the CPUs the check may run on, which every case inherits and `os.sched_getaffinity()` reports, are 16 or fewer.

Timing is calibrated in the same check. `hidden/reference_client.py`, a correct sweep at the documented limit, runs first against the main dataset, up to three times, stopping once its best time is well clear of the floor, and once against the outage. The main case's time limit is 20 seconds or 5 times the reference's best time, whichever is longer; the outage's is 5 times the reference's time on it (the ticket's budget is for the network as it is). A sequential client cannot beat the floor (44.95 s: the answering docks' latencies, which the gateway sleeps, plus the slowest answering dock's latency for each dock that must be reported offline), however idle the host. When 5 times the reference's best time reaches the floor (a reference time of 8.99 s), the check raises and the run is invalid. The reference must also give the exact report with nothing refused and nothing held, or the check raises. The main and all-answering cases are killed only at twice the floor (89.9 s), so a correct but slow sweep finishes and fails `within_budget` alone; the outage is killed 10 s past its time limit, and its report is judged only when it finished within that limit.

Required:

- `answered_docks_correct`: one line per dock in ID order, each answering dock's line exactly as `show` prints it ("1 bike" singular included), in the main, all-answering, and outage cases.
- `failures_handled`: offline and failed lines as the ticket gives them, the summary line, exit 1 (main, outage) and 0 (all answering), and exit 2 within 10 s with no gateway.
- `within_budget`: the main case exits by itself within its time limit, having asked for every dock, and the outage within its own.
- `within_limit`: the gateway refused nothing in the main, all-answering, and outage cases, and the main case asked for at least one dock.
- `no_held_requests`: no request held in progress longer than 8 s in those cases, and the main case asked for at least one dock.
- `no_work_after_exit`: no request or connection reached the gateway after the command exited, and no process was left, in every case; the main case asked for at least one dock.
- `existing_commands_unchanged`: `list` and `show` behave as the fixture's tests expect, run as commands (observed from outside, so a change to the package's internal signatures that keeps the behavior is not held against it).

Measures, deciding nothing: `main_seconds`, `time_limit_seconds`, `hard_limit_seconds`, `reference_seconds`, `reference_runs`, `sequential_floor_seconds`, `outage_seconds`, `outage_time_limit_seconds`, `outage_reference_seconds`, `main_exit`, `main_killed`, `allok_seconds`, `outage_exit`, `outage_killed`, `down_exit`, `down_seconds`, `peak_in_progress`, `outage_peak_in_progress`, `most_attempted_at_once`, `refused`, `outage_refused`, `abandoned_requests`, `outage_abandoned_requests`, `held_requests`, `outage_held_requests`, `longest_request_seconds`, `outage_longest_request_seconds`, `reference_longest_request_seconds`, `in_progress_at_exit`, `mean_requests_in_progress`, `requests_total`, `list_requests`, `docks_asked`, `most_requests_for_one_dock`, `late_requests`, `survivors`, `cpus_available`, `cpu_count_seen`, `problems`, `main_stderr_tail`, `fixture_tests` (the fixture's own 15 tests from the check's copies against the agent's package), `own_suite` (the agent's whole suite as it left it), `commits_added`, `final_words`.

## Reference behaviors

`qualify/plan.json` runs each arm with the command executor. Last run: `~/.cache/agent-trials/qualify-async-fanout-py-20261001-155657`, run alongside the Go scenario's qualification (8 checks at once; load average 20 to 55 on the 24-core host). Every arm matched the plan's note. Seconds are main / outage; refused and held are main and all-answering / outage.

| Arm | What it is | answered | failures | budget | limit | held | after exit | existing | Passes | Seconds | Refused | Held |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `good` | thread pool at 16, urllib timeout of 2 s per read | yes | yes | yes | yes | yes | yes | yes | yes | 3.5 / 6.4 | 0 / 0 | 0 / 0 |
| `good-asyncio` | hand-written asyncio streams, `Semaphore(16)`, `wait_for` inside the semaphore, connection closed in `finally` | yes | yes | yes | yes | yes | yes | yes | yes | 3.5 / 6.4 | 0 / 0 | 0 / 0 |
| `good-workers` | 8 worker threads on a queue, each with one keep-alive connection, replaced after a silent dock | yes | yes | yes | yes | yes | yes | yes | yes | 6.6 / 12.4 | 0 / 0 | 0 / 0 |
| `good-strict-api` | `good`, with every gateway call made to state its timeout (the fixture's unit tests no longer match its signatures: `fixture_tests` fails) | yes | yes | yes | yes | yes | yes | yes | yes | 3.6 / 6.5 | 0 / 0 | 0 / 0 |
| `sequential` | one dock after another, 2-second timeout (also `bad.sh`) | yes | yes | no | yes | yes | yes | yes | no | 51.2 / killed | 0 / 0 | 0 / 0 |
| `unbounded` | a thread per dock | no | no | yes | no | yes | yes | yes | no | 2.2 / 2.2 | 201 / 181 | 0 / 0 |
| `default-pool` | `good` with the pool at Python's default size (32 here) | no | no | yes | no | yes | yes | yes | no | 2.4 / 2.3 | 171 / 176 | 0 / 0 |
| `affinity-pool` | `good` with one worker per CPU the process may use (24 here) | no | no | yes | no | yes | yes | yes | no | 2.2 / 2.4 | 134 / 172 | 0 / 0 |
| `no-timeout` | pool at 16, the client as it is | yes | no | no | yes | no | yes | yes | no | 60.5 / killed | 0 / 0 | 4 / 16 |
| `abandoned` | `Semaphore(16)` and `wait_for(to_thread(read), 2)` with no socket timeout | no | no | no | no | no | yes | yes | no | 60.6 / killed | 53 / 150 | 4 / 13 |
| `abandoned-daemon` | each read in a daemon thread joined for 2 s under a semaphore of 16 | no | no | yes | no | yes | yes | yes | no | 3.6 / 4.5 | 53 / 139 | 0 / 0 |
| `abandoned-daemon-cap10` | `abandoned-daemon` with 10 reads at a time | no | no | yes | no | yes | yes | yes | no | 5.3 / 6.6 | 0 / 130 | 0 / 0 |
| `paced` | `good`'s client, a thread per dock started 40 a second | no | no | yes | no | yes | yes | yes | no | 5.5 / 5.5 | 0 / 52 | 0 / 0 |
| `pool-holds` | a fixed pool of 16 workers with a 30 s backstop per read; the main thread gives each dock 2 s from when its read began, then moves on and exits at once | yes | yes | no | yes | no | yes | yes | no | 4.0 / 34.7 | 0 / 0 | 0 / 16 |
| `overall-deadline` | reads in daemon threads under a semaphore of 16 with no timeout each, the whole sweep given 12 s | no | no | yes | yes | no | yes | yes | no | 12.2 / 12.1 | 0 / 0 | 4 / 15 |
| `long-timeout` | `good` with 10 s before a dock counts as offline | yes | no | yes | yes | no | yes | yes | no | 10.6 / 21.3 | 0 / 0 | 4 / 20 |
| `leaks` | `good`, then a detached helper re-reads offline docks for a few seconds | yes | yes | yes | yes | yes | no | yes | no | 3.5 / 6.4 | 0 / 0 | 0 / 0 |
| `wrong` | errors printed as offline, exit 0 always | yes | no | yes | yes | yes | yes | yes | no | 3.5 / 6.4 | 0 / 0 | 0 / 0 |
| `noop` | nothing | no | no | no | no | no | no | yes | no | 0.1 / 0.1 | 0 / 0 | 0 / 0 |

The arms over the limit also fail the report checks, because the gateway really answers 429 past it. `no-timeout` and `abandoned` finish the main case only after the gateway's 60 s (`abandoned` because `asyncio.run` waits for the worker threads it gave up on) and are killed in the outage; `no-timeout` prints offline docks as `failed (HTTP 504)`. `abandoned-daemon` exits on time, so only the gateway's count catches it; its given-up requests stay in progress until it exits, so `no_held_requests` can fail too when a case runs past 8 s (it did for `abandoned-daemon-cap10` in an earlier run at load average 77 to 100). `pool-holds` holds 16 requests on silent docks for its 30 s backstop in the outage and so fails `no_held_requests` whatever the host's load; its outage takes about 35 s, so `within_budget` passes or fails depending on whether 5 times the reference's outage time is above that (it was 31.7 s in this run). `overall-deadline` and `long-timeout` hold requests on offline docks for 12 and 10 s.

Stability: `~/.cache/agent-trials/robust-async-fanout-py-20261001-160314` repeats `good`, `good-asyncio`, `good-workers`, `good-strict-api`, and `pool-holds` three times, run alongside the Go scenario's (13 checks at once, load average 37 to 55): the four correct arms passed 12/12 with no request in progress longer than 2.03 s (the reference's longest 2.15 s), and `pool-holds` failed `no_held_requests` 3/3 with 16 held requests each time (and `within_budget` 3/3: outage 34.7 to 35.0 s against limits of 33.0 to 34.5 s). `~/.cache/agent-trials/loaded-async-fanout-py-20261001-160652` repeats the four correct arms four times (14 checks at once, load average 15 to 30): 16/16, longest request 2.03 s. Neither round reached the load of the failure described next.

An earlier run of this plan, before the slow docks were narrowed from 1.0-1.5 s to 1.0-1.2 s, at load average 77 to 100, had `good-asyncio` report one slow dock (1.40 s) as offline in the outage: the client's and the gateway's overhead under that load used up the 0.6 s left before the ticket's 2 seconds. The narrower range leaves at least 0.8 s.

## Running it

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/scenarios/async-fanout-py/qualify/plan.json --jobs 4
```

The check needs bubblewrap, `/usr/bin/python3` (3.10 or later), and more than 16 CPUs whatever the plan's `sandbox` setting. Agent arms need nothing readable beyond the default confinement. A check takes about 35 s for a good solution and up to about 130 s for one that waits out the gateway's 60 s or runs sequentially.
