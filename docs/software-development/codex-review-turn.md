# Review turn for Codex

[`codex-review-turn/stop.py`](codex-review-turn/stop.py) is a Codex `Stop` hook. The first time a turn is about to end, it returns `{"decision": "block", "reason": ...}` with a review request, so the agent reviews its work and then finishes; the second stop of the turn goes through (`stop_hook_active`, and a marker per turn id). A turn whose repository shows no changes (a question, a plan) ends without the review. The request asks the agent to bring other places that implement or depend on its change into agreement, to check the change under the conditions its callers will run it in, and to check that its tests exercise what the request relies on.

## Evidence

Trials in this repository, gpt-6-luna at low effort, against two copies of the unchanged instructions (baseline). Design: seven design and concurrency tasks where it still fails often. Clean change: a sound change whose report should state what was done and checked, nothing more.

| Delivery | Design | Clean change | Unrun check disclosed |
|---|---|---|---|
| Baseline | 30.5 of 56 | 6 of 6 | 24 of 24 |
| This hook | 45 of 56 | 6 of 8 | 8 of 8 |
| The same review asked as a standing instruction | 31 of 55 | | |

The review changes outcomes only as a step the agent cannot skip; as a sentence in its instructions it does nothing. Its cost: about twice the output tokens and 1.8 times the time per task, and on the clean change two of eight reviewed reports claimed a check (`make check`) the agent had not fully run. Asking the reply to say what was and was not checked made it worse in every family tested (clean change 2 of 6 for this executor, 2 of 11 across three Claude models), so the review asks nothing of the reply. On Claude models the design gain was small (8 against 6 of 9 at medium effort on the larger model, 3 against 3 of 6 on the largest at low effort), so the hook is offered for Codex.

## Enabling and disabling

Copy `stop.py` somewhere stable, such as `~/.codex/hooks/review-turn-stop.py`, and add to `~/.codex/config.toml` (or a repository's `.codex/config.toml` to limit it to that repository):

```toml
[[hooks.Stop]]

[[hooks.Stop.hooks]]
type = "command"
command = 'python3 "$HOME/.codex/hooks/review-turn-stop.py"'
timeout = 30
statusMessage = "Review before finishing"
```

Codex asks for trust before a new hook runs. Remove the block to disable it.
