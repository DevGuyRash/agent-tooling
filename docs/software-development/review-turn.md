# Review turn

The Software Development plugin ships [`hooks/review-turn-stop.py`](../../plugins/software-development/hooks/review-turn-stop.py), a `Stop` hook that installs with the plugin and acts only where the harness's stop event names the turn (a `turn_id`). The first time a turn is about to end, it returns `{"decision": "block", "reason": ...}` with a review request, so the agent reviews its work and then finishes; the second stop of the turn goes through (`stop_hook_active`, and a marker per turn id). The review is asked of a turn that leaves uncommitted changes, or whose checked-out history gained a commit dated in a later second than the one the turn began in (git keeps whole seconds, and the start is the earliest record in the session's transcript that names the turn in a turn-id field), so a turn that commits its work is still reviewed; other turns (a question, a plan) end without it. Commit times are the measure, so a commit another process adds to the checked-out branch during the turn counts too, and a pull of commits made earlier does not. The request asks the agent to bring other places that implement or depend on its change into agreement, to check the change under the conditions its callers will run it in, and to check that its tests exercise what the request relies on.

## Evidence

Trials in this repository, gpt-6-luna at low effort, against two copies of the unchanged instructions (baseline). Design: seven design and concurrency tasks where it still fails often. Clean change: a sound change whose report should state what was done and checked, nothing more.

| Delivery | Design | Clean change | Unrun check disclosed |
|---|---|---|---|
| Baseline | 30.5 of 56 | 6 of 6 | 24 of 24 |
| This hook | 45 of 56 | 6 of 8 | 8 of 8 |
| The same review asked as a standing instruction | 31 of 55 | | |

The review changes outcomes only as a step the agent cannot skip; as a sentence in its instructions it does nothing. Its cost: about twice the output tokens and 1.8 times the time per task, and on the clean change two of eight reviewed reports claimed a check (`make check`) the agent had not fully run. Asking the reply to say what was and was not checked made it worse in every family tested (clean change 2 of 6 for this executor, 2 of 11 across three Claude models), so the review asks nothing of the reply. On Claude models the design gain was small (8 against 6 of 9 at medium effort on the larger model, 3 against 3 of 6 on the largest at low effort); the harness those models ran under has no turn in its stop event, so the hook does nothing there.

## Enabling and disabling

Installing or updating the plugin installs the hook wherever the harness runs a plugin's hooks. A harness may ask for trust before it first runs it; declining trust, or disabling the plugin, turns it off. A harness that runs stop hooks only from its own configuration can run the same script from there, with a 30-second timeout.
