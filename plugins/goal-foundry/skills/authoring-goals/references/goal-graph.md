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
