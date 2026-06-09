# Goal Graph

`.goals/graph.json` is the machine-readable goal set. `GOALS.md` is the human-readable registry.

Recommended node fields:

```json
{
  "id": "G-014",
  "title": "Fix password reset flow",
  "status": "ready",
  "type": "bugfix",
  "source": ["tests/auth/reset.test.ts"],
  "contract": ".goals/current.md",
  "risk": "medium",
  "verifier": "auth regression test + auth suite",
  "depends_on": [],
  "blocks": [],
  "follow_up_to": null,
  "spawned_from": "G-013",
  "updated_at": "2026-06-06"
}
```

Status values: `candidate`, `ready`, `active`, `conditional`, `blocked`, `completed`, `abandoned`, `superseded`, `duplicate`, `maintenance-loop`, `not-launchable`.

Edges should model `depends_on`, `blocks`, `duplicates`, `supersedes`, `follow_up_to`, `spawned_from`, `part_of`, and `conflicts_with` when relevant.

The document also carries a `schema` field (`goalspec.graph.v1`), a `created` date, a `nodes` map keyed by goal id, and an `edges` list. Maintain it with `scripts/graph_goal.py` (`--add-contract <file>`, `--edge FROM TYPE TO`); `scripts/select_goal.py` reads it to pick the next ready, unblocked, low-risk goal. Example edges:

```json
"edges": [
  {"from": "G-014", "type": "depends_on", "to": "G-013"},
  {"from": "G-015", "type": "duplicates", "to": "G-014"}
]
```
