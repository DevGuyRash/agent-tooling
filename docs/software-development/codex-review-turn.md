# Review turn for Codex

[`codex-review-turn/stop.py`](codex-review-turn/stop.py) is a Codex `Stop` hook. The first time a turn is about to end, it returns `{"decision": "block", "reason": ...}` with a review request, so the agent reviews its work and then finishes; the second stop of the turn goes through (`stop_hook_active`, and a marker per turn id). A turn whose repository shows no changes (a question, a plan) ends without the review. The request asks the agent to bring other places that implement or depend on its change into agreement, to check the change under the conditions its callers will run it in, to check that its tests exercise what the request relies on, and to make its reply say what it checked and what it did not.

## Evidence

Trials in this repository, gpt-6-luna at low effort on seven design and concurrency tasks where it still fails often, each against two copies of the unchanged instructions:

| Delivery | Passes | Baseline |
|---|---|---|
| The review as a forced follow-up turn | 86 of 112 | 61 of 112 |
| The review through this hook | 42 of 56 | 30.5 of 56 |
| The same words as a standing instruction | 31 of 55 | 30.5 of 56 |

The review changes outcomes only as a step the agent cannot skip; as a sentence in its instructions it does nothing. It costs about twice the output tokens and 1.8 times the time per task. On Claude Haiku the same review turn did not make it disclose an unrun check (4 of 12) and made its replies on a clean change fail (2 of 6), so it is offered for Codex only.

The hook was verified through a Codex configuration file, as below. Whether a Codex plugin can ship it was not checked: codex-cli 0.160 lists its `plugin_hooks` feature switch as removed while still carrying plugin-hook loading and trust, so the plugin route stays untested here.

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
